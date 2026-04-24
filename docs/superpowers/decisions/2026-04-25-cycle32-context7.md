# Cycle 32 — Step 6 Context7 Verification

**Date:** 2026-04-25 · **Library:** `/pallets/click` (Context7 ID) · **Pinned version:** Click 8.3.2 (installed).

Per cycle-31 L1 MANDATORY Step 6 when design references library-API kwargs. Checks from C4.

## Check 1 — `click.File` parameters

**Design reference:** `click.File("r", lazy=False, encoding="utf-8")` for `--content-file` and `--extraction-json-file`.

**Context7 result:** Click docs show `click.File('r')` as canonical usage with `-`=stdin native support:
```python
@click.argument('input', type=click.File('r'))
# ...
$ echo "hello world" | python process.py - output.txt
```

Signature: `click.File(mode='r', encoding=None, errors='strict', lazy=None, atomic=False)`. `lazy` defaults to `None` (inferred: False for read modes, True for write). `encoding` defaults to None (uses Python's default UTF-8 on Python 3).

**Verdict:** No conflict. `lazy=False` explicit is redundant-but-harmless (matches default for read). `encoding="utf-8"` explicit is similarly redundant on modern Python but documents intent.

**Action:** Keep design as-specified; both kwargs pass through Click's `__init__`.

## Check 2 — `click.Path` directory constraint

**Design reference:** `click.Path(exists=True, file_okay=False)` for `--wiki-dir`.

**Context7 result:** Canonical example:
```python
@click.argument('directory', type=click.Path(exists=True, file_okay=False, dir_okay=True))
```

**Verdict:** Exact match. `exists=True` + `file_okay=False` means "must exist AND must be a directory" (dir_okay defaults to True). Click rejects file paths with a UsageError before the callback fires.

**Action:** Keep design as-specified.

## Check 3 — Boolean flag `--flag/--no-flag` syntax

**Design reference:** `"--incremental/--no-incremental", default=True` on `kb compile-scan`.

**Context7 result:** Canonical example:
```python
@click.option('--shout/--no-shout', default=False)
def info(shout):
    ...
```

Click docs: "Click automatically sets `is_flag=True` and handles the default." So `"--foo/--no-foo"` is a single option declaration that defines BOTH the positive and negative forms.

**Verdict:** Exact match. The syntax is preferred over manual `is_flag=True + default=True` with separate `--no-flag` handling. Already used at `cli.py:417` in cycle-15 `kb publish`.

**Action:** Keep design as-specified.

## Check 4 — `CliRunner` stdin simulation (for AC5 test)

**Design reference:** `runner.invoke(cmd, input=content)` to test `--content-file -` stdin mode.

**Context7 result:** Canonical example:
```python
result = runner.invoke(hello, input='John\n')
```

**Verdict:** Standard CliRunner API. Works transparently with `click.File('r')` when the user passes `-` as the file argument — Click routes stdin through the mock.

**Action:** Keep AC5 test plan as-specified (stdin test for `--content-file -`).

## Summary

All four library-API references in the cycle 32 design match documented Click 8.3 behaviour. No design amendments needed. Step 7 plan drafting proceeds.
