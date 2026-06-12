# token_delimit.py / test_token_delimit.py — Reference

## What `token_delimit.py` does

Inserts `;` statement delimiters into T-SQL text. It walks sqlglot's **token
stream** (not its parser) and places a `;` before every token that begins a new
statement, descending into `BEGIN/END`, `BEGIN TRY/CATCH`, `IF/WHILE`, and
procedure bodies.

## How it does it

1. Tokenises the SQL with sqlglot.
2. Walks the tokens tracking: parenthesis depth, a block stack
   (`BEGIN`/`CASE`/`TRY`/`CATCH` via token type), the previous significant
   token, and the keyword leading the current statement.
3. At depth 0, a token whose text is in `STARTERS` marks a statement boundary,
   **unless** a suppression rule applies (it is a sub-clause / continuation:
   `INSERT…SELECT`, `UPDATE…SET`, CTE body, `UNION ALL`, `IF/WHILE/ELSE` body,
   `DROP TABLE IF EXISTS`, `WITH RECOMPILE`, table hints `WITH (NOLOCK)`,
   `OFFSET…FETCH`, string literals containing keywords, `@`-vars named after
   keywords).
4. Records each boundary as a `TokInsertion`; `apply()` writes the `;`s in.

## API

### `annotate(sql, dialect="tsql", terminate_all=False, conservative=False) -> (insertions, sql)`
Returns the list of `TokInsertion` boundaries.

- `dialect` — sqlglot dialect; `"tsql"` or `""`.
- `terminate_all=False` — `;` only *between* statements.
- `terminate_all=True` — also terminate the last statement of each block (before
  block-closing `END`/`END CATCH`) and at end of input. Never before `END TRY`
  or `CASE…END`.
- `conservative=False` — delimit every detected boundary.
- `conservative=True` — high-confidence starters always delimited; low-confidence
  starters (`SELECT, SET, EXEC, EXECUTE, IF, WHILE, WITH, RETURN, FETCH, ELSE`)
  delimited only if **corroborated** (keyword starts its physical line, OR the
  text before it parses as one complete statement). Uncorroborated ones are
  marked `flagged` and **not** written.

### `apply(sql, insertions, annotate_marker=False, marker="[AUTOMATED DELIMITER]") -> str`
Writes the `;`s into the text. Skips spots already ending in `;` and skips
`flagged` insertions.

- `annotate_marker=False` — write a bare `;`.
- `annotate_marker=True` — write `;  /* <marker> */` (bounded block comment, so
  same-line code after it is preserved).
- `marker` — inner marker text.

### `review(sql, insertions, context=40, verbose=True) -> list[dict]`
Pre-apply. Returns insertions landing immediately after an operator
(`+ = , ( …`). Dicts: `line, col, before_keyword, prev_char, context`.
`verbose=False` suppresses printing.

### `flagged_cuts(insertions, sql=None, verbose=True) -> list[dict]`
Returns the `flagged` insertions (conservative mode: suspected boundary, not
cut). Pass `sql` to include a `context` snippet. Dicts: `line, col,
before_keyword[, context]`.

### `check_midline_cut(text_or_path, marker="[AUTOMATED DELIMITER]", is_path=False, verbose=True) -> list[dict]`
Post-apply. Returns delimiters with real code on both sides of one physical line.
Takes the **inner** marker text. Dicts: `line, after, full_line`.

- `is_path=False` — first arg is text.
- `is_path=True` — first arg is a file path.

### `check_commented_out(...)`
Legacy, for the old `--` marker. Not used with the `/* … */` marker.

### `TokInsertion` (dataclass)
`offset, line, col, before_keyword, note, flagged=False`.

### Tunable constants
`STARTERS`, `LOW_CONFIDENCE`, `SUPPRESS_PREV`, `NON_STARTER_TYPES`,
`DDL_OBJECT_TYPES`.

## How to run

```python
import token_delimit as T
sql = open("file.sql", encoding="utf-8", errors="replace").read()
ins, _ = T.annotate(sql, dialect="tsql", terminate_all=True, conservative=True)
fixed  = T.apply(sql, ins, annotate_marker=True, marker="[AUTOMATED DELIMITER]")
```

CLI:
```bash
python token_delimit.py            # see module __main__ for flags
```

---

## What `test_token_delimit.py` does

Standalone regression suite for `token_delimit.py`. Runs built-in SQL inputs
through `annotate`/`apply` and asserts the output. Covers the spec issues,
nested `IF/ELSE` and `TRY/CATCH`, multi-param procs, `CTE + UPDATE`, comments
between statements, consecutive `IF…DROP`, `@end`-style params, and the four
conservative-mode cases. Does not touch external `.sql` files.

## How to run

```bash
python test_token_delimit.py
```
or in a notebook cell:
```python
!python test_token_delimit.py
```

Both files must be in the same directory (or `token_delimit.py` on
`PYTHONPATH`). Prints one line per case and a `N passed, M failed` summary;
exits non-zero if any fail.
