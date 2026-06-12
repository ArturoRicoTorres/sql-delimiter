#!/usr/bin/env python3
"""Regression tests for token_delimit.py.

Run:  python test_token_delimit.py
Each test applies the delimiter (bare ';', no marker) and asserts which
substrings MUST and MUST NOT appear. Covers the 8 reported issues plus nested
IF/ELSE, nested TRY/CATCH, many-parameter procedures, CTE+UPDATE, comments
between statements, and multi-line statements.
"""
import logging
logging.getLogger("sqlglot").setLevel(logging.ERROR)
import token_delimit as T


def run(sql, *, terminate_all=False):
    ins, _ = T.annotate(sql, "tsql", terminate_all=terminate_all)
    return T.apply(sql, ins, annotate_marker=False)


CASES = []
def case(name, sql, must=None, must_not=None, terminate_all=False):
    CASES.append((name, sql, must or [], must_not or [], terminate_all))


# --- Issue 1: IF condition must not be cut from its controlled stmt/block ---
case("1a IF EXISTS ... INSERT",
     "if exists (select top 1 1 from #p as p where p.t = 'x')\ninsert into #d select 1",
     must_not=["')\n;", "');", "'x');"])           # no ';' right after the condition
case("1b multi-line IF ... BEGIN",
     "if (@b = 'Alles'\n or @b = 'Met dagtekening')\nbegin\nselect 1\nend",
     must_not=["');", ")\n;", ");\nbegin", ") ;"])
case("1c nested IF",
     "if @a=1 if @b=2 select 1",
     must_not=["if @a=1;", "@a=1 ;", "if @b=2;"])

# --- Issue 2: IF/ELSE/WHILE control flow ---
case("2a IF ... ELSE bare pairing preserved (no ';' before ELSE)",
     "if @x=1 select 1 else select 2 select 3",
     must=["select 2; select 3", "; select 3"],     # construct separated from next stmt
     must_not=["select 1; else", "1;else", "select 1 ; else"])
case("2b WHILE body not cut",
     "while @i < 10 set @i = @i + 1",
     must_not=["10;", "< 10 ;"])
case("2c IF/ELSE with BEGIN/END: inner stmts delimited, no ';' before ELSE",
     "if @x=1\nbegin\nselect 1\nset @y=2\nend\nelse\nbegin\nselect 2\nend",
     must=["select 1;", "set @y=2;"],
     must_not=["end;\nelse", "end; else", "end ;else"],
     terminate_all=True)

# --- Issue 3: TRY/CATCH must not break; no ';' between END TRY and BEGIN CATCH ---
case("3a no ';' between END TRY and BEGIN CATCH",
     "begin try\nselect 1\nend try\nbegin catch\nselect 2\nend catch",
     must_not=["end try;", "try; begin", "try;\nbegin"])
case("3b nested TRY/CATCH inner stmts terminated",
     "begin try\nbegin try\nselect 1\nend try\nbegin catch\nselect 2\nend catch\nend try\n"
     "begin catch\nselect 3\nend catch",
     must=["select 1;", "select 2;", "select 3;"],
     must_not=["end try;"],
     terminate_all=True)

# --- Issue 4: never split a @parameter / identifier ---
case("4a @end parameter not split",
     "create procedure p\n  @start date = null\n, @end date = null\nas\nselect 1",
     must_not=["@;", "@ ;", "@; end", "@ end"],
     terminate_all=True)
case("4b @return / @select variables not split",
     "declare @select int, @return int = 0\nset @select = 1",
     must_not=["@;", "@ select", "@ return"])

# --- Issue 5: CREATE PROCEDURE header is one unit (no split before WITH/AS) ---
case("5a no split before WITH RECOMPILE",
     "create procedure [r].[p]\n( @k int , @m varchar(50) = 'B' )\nwith recompile\nas\nselect 1",
     must_not=[");", ") ;", ")\n;"])
case("5b no split before AS",
     "create procedure p @a int\nas\nselect 1",
     must_not=["int;", "@a int ;", "int;\nas"])
case("5c WITH ENCRYPTION header intact",
     "create procedure p @a int with encryption as select 1",
     must_not=["int;", "int ; with"])

# --- Issue 6: UPDATE variants terminated ---
case("6a UPDATE ... FROM ... JOIN ... WHERE then next stmt",
     "update t set col = x from t1 t inner join t2 s on t.id=s.id where t.a=1 select 2",
     must=["where t.a=1; select 2", "=1; select"])
case("6b simple UPDATE then next stmt",
     "update t1 set col = value select 2",
     must=["value; select 2"])
case("6c UPDATE not cut internally",
     "update t set a=1 from u where a=2",
     must_not=["update t;", "set a=1;", "from u;"])

# --- Issue 7: comments between statements; SELECT INTO terminated ---
case("7 comment between statements, SELECT INTO terminated",
     "DROP TABLE IF EXISTS #tmp;\nSELECT c1 INTO #tmp FROM S\n-- note; with semicolon in comment\nINSERT INTO O VALUES ('done')",
     must=["FROM S;"],                      # ';' terminates SELECT INTO right after S
     must_not=["#tmp;;", "INTO #tmp;"])     # not double-terminated, not split mid-statement

# --- Issue 8: IF/ELSE branch handling (valid form) ---
case("8 IF/ELSE branch stmts in blocks get delimited",
     "if @x=1\nbegin\nselect 1\nend\nelse\nbegin\nselect 2\nend",
     must=["select 1;", "select 2;"],
     must_not=["end;\nelse", "end; else"],
     terminate_all=True)

# --- Additional: many-param proc, CTE+UPDATE, multi-line ---
case("A1 many-parameter procedure header intact",
     "create procedure p\n  @a int\n, @b int = 0\n, @c date = null\n, @d varchar(10)\n, @end date = null\nas\nselect 1",
     must_not=[";\nas", "@;", "(10);", "null;\n, @"])
case("A2 CTE followed by UPDATE (one statement, not split)",
     "with c as (select id from t) update u set x=1 from u join c on u.id=c.id",
     must_not=[");\nupdate", "); update", ") update;"])
case("A3 multi-line SELECT then INSERT",
     "select a, b\nfrom t\nwhere a=1\ninsert into u values (1)",
     must=["where a=1; insert", "=1; insert"])
case("A4 consecutive SELECTs split",
     "select 1 select 2 select 3",
     must=["select 1; select 2; select 3"])

# --- Regressions for issues found in real files ---
case("R1 consecutive IF ... DROP not cut (each IF+body one stmt)",
     "if object_id('tempdb..#a') is not null drop table #a\n"
     "if object_id('tempdb..#b') is not null drop table #b\n"
     "if object_id('tempdb..#c') is not null drop table #c",
     must=["#a;", "#b;"],                       # delimiter AFTER each full IF..DROP
     must_not=["is not null;", "null;  drop", "null; drop"])  # never between cond and DROP
case("R2 standalone IF after a DROP statement not treated as DDL clause",
     "drop table #t if @x = 1 select 1",
     must_not=["#t if", "if @x = 1; select"])   # the IF's body is its own, not cut
case("R3 @end parameter never split (terminate_all)",
     "create procedure p\n  @start date = null\n, @end date = null\n, @end2 int = 0\nas\nselect 1",
     must_not=["@;", "@ ;", "@; end", "@ end ", "@;end"],
     terminate_all=True)


# --- Conservative mode: low-confidence boundaries require corroboration ---
# Each case: (name, sql, expected_applied_substrings, expected_flagged_keywords)
CONS_CASES = []
def cons_case(name, sql, applied_must=None, applied_must_not=None, flagged=None):
    CONS_CASES.append((name, sql, applied_must or [], applied_must_not or [], flagged or []))

cons_case("C1 high-confidence stmts identical to default (no flags)",
          "insert into t (a) values (1) update t set a=2 delete from t where a=2",
          applied_must=["values (1); update", "a=2; delete"], flagged=[])
cons_case("C2 line-start SELECTs corroborated and delimited",
          "select 1\nselect 2\nselect 3",
          applied_must=["select 1; select 2", "select 2; select 3"], flagged=[])
cons_case("C3 same-line stmts rescued by parseable prefix",
          "set @x = 1 set @y = 2",
          applied_must=["set @x = 1; set @y = 2"], flagged=[])
cons_case("C4 mid-line low-confidence, unparseable prefix -> flagged not cut",
          "update t set a = select 1",
          applied_must_not=["a =; select", "a = ; select"], flagged=["SELECT"])


def run_conservative():
    passed = failed = 0
    for name, sql, amust, amustnot, fexp in CONS_CASES:
        ins, _ = T.annotate(sql, "tsql", conservative=True)
        out = T.apply(sql, ins, annotate_marker=False)
        norm = " ".join(out.split())
        got_flags = sorted(i.before_keyword for i in ins if i.flagged)
        errs = []
        for m in amust:
            if m not in out and " ".join(m.split()) not in norm:
                errs.append(f"missing applied {m!r}")
        for m in amustnot:
            if m in out or " ".join(m.split()) in norm:
                errs.append(f"unexpected applied {m!r}")
        if got_flags != sorted(fexp):
            errs.append(f"flags {got_flags} != expected {sorted(fexp)}")
        # a flagged boundary must NEVER appear as a real cut in the output
        if any(i.flagged for i in ins) and out != T.apply(sql, [i for i in ins if not i.flagged]):
            errs.append("flagged insertion altered output (was applied)")
        if errs:
            failed += 1
            print(f"FAIL  {name}")
            for e in errs:
                print(f"        {e}")
            print(f"        got: {out!r}  flags={got_flags}")
        else:
            passed += 1
            print(f"pass  {name}")
    return passed, failed


def main():
    passed = failed = 0
    for name, sql, must, must_not, ta in CASES:
        out = run(sql, terminate_all=ta)
        norm = " ".join(out.split())          # whitespace-insensitive for some checks
        errs = []
        for m in must:
            if m not in out and " ".join(m.split()) not in norm:
                errs.append(f"missing {m!r}")
        for m in must_not:
            if m in out or " ".join(m.split()) in norm:
                errs.append(f"unexpected {m!r}")
        if errs:
            failed += 1
            print(f"FAIL  {name}")
            for e in errs:
                print(f"        {e}")
            print(f"        got: {out!r}")
        else:
            passed += 1
            print(f"pass  {name}")
    cp, cf = run_conservative()
    passed += cp
    failed += cf
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
