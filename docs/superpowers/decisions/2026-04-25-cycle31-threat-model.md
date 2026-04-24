# Cycle 31 — Threat Model

**Date:** 2026-04-25
**Scope:** Three new thin CLI subcommand wrappers over existing page_id-input MCP
tools, plus one shared helper:

1. `kb read-page <page_id>` → forwards to `kb_read_page` (`src/kb/mcp/browse.py:86`)
2. `kb affected-pages <page_id>` → forwards to `kb_affected_pages` (`src/kb/mcp/quality.py:265`)
3. `kb lint-deep <page_id>` → forwards to `kb_lint_deep` (`src/kb/mcp/quality.py:130`)
4. Shared helper `_is_mcp_error_response(output)` in `src/kb/cli.py`

**Pattern precedent:** cycle 27 AC1-AC4 wrappers (`src/kb/cli.py:568-695`) and
cycle 30 AC2-AC6 wrappers (`src/kb/cli.py:698-832`).

---

## Analysis

The attack surface introduced this cycle is narrow by design. Each wrapper is a
thin Click shim that (1) accepts a single positional `page_id` argument, (2)
calls the respective `kb.mcp.*` tool function via a function-local import to
preserve the cycle-23 AC4 boot-lean contract (`kb --version` must not import
heavy transitive deps), (3) inspects the returned string for an error prefix,
and (4) writes to stdout or stderr and exits 0 or 1 accordingly. Because the
MCP tools already perform `_strip_control_chars` + `_validate_page_id` +
`_sanitize_error_str`, the wrappers must NOT re-implement any of that logic;
doing so invites divergence, which is the single largest threat class here
(T7). The correct posture is "forward raw input; rely on MCP-tool validation;
classify output by prefix; never re-format or re-wrap error text." Any CLI-side
logic that mutates `page_id` between Click arg-parse and the MCP call (e.g., a
well-meaning `.strip()` or a `Path` normalization) will drift behaviour
relative to the MCP tool and must be rejected at review.

The second-order risks cluster around the new shared discriminator
`_is_mcp_error_response(output)`. The three tools collectively emit THREE
error-prefix shapes — `"Error:"` (colon form from `_validate_page_id`, config-
driven caps, and re-raised library errors), `"Error <verb> ..."` (space form
from the `Error reviewing`, `Error checking fidelity for`, `Error computing
affected pages` templates in `src/kb/mcp/quality.py:56,59,149,152,290`), and
`"Page not found:"` (the distinctive shape emitted by `kb_read_page` at
`src/kb/mcp/browse.py:125`, which is the primary reason a simple
`startswith("Error:")` check is insufficient for cycle-31). If
`_is_mcp_error_response` is too narrow (e.g., matches only `"Error:"`), the
`"Page not found:"` case will exit 0 with the page-not-found text printed to
stdout — a silent failure that breaks pipes like `kb read-page X > page.md`.
If the discriminator is too wide (e.g., matches any line containing `"Error"`
or any line starting with `"Error"` without a colon/space/bracket follower), a
legitimate page body whose first line happens to be `"Error handling in
Python"` (title of a concepts page) would be misclassified as an error and
exit 1. The verification checklist must therefore pin BOTH the positive set
(all three shapes match) AND the negative set (false-positive page bodies do
NOT match).

Three smaller concerns round out the model. First, `kb_read_page` already caps
its output at `QUERY_CONTEXT_MAX_CHARS * 4 + 4096` bytes with an explicit
truncation footer, so the CLI wrapper inherits that bound for free — no new DoS
surface relative to the existing MCP channel, but the verification must pin
that the cap is not bypassed by the wrapper (e.g., by re-reading the file
directly). Second, `_validate_page_id` is called with `check_exists=False` by
`kb_read_page` (the tool performs its own case-insensitive fallback) and
`check_exists=True` by the other two. The wrappers must not attempt to
pre-validate or pre-check — doing so would either (a) duplicate the guard (no
harm) or (b) subtly differ (divergence bug). The correct wrapper body forwards
the raw arg. Third, the boot-lean contract (`kb --version` short-circuits
BEFORE `kb.config` is imported, `src/kb/cli.py:15-19`) demands that every new
wrapper's `kb.mcp.*` import sits INSIDE the function body with a `# noqa:
PLC0415` suppression — a module-level `from kb.mcp.quality import ...` would
eagerly pull `frontmatter`, `yaml`, `kb.feedback.reliability`, and the entire
review-context chain at `kb --version` time, which is the cycle-23 AC4/AC5
regression we have explicit pytest coverage against.

---

## 1. Trust boundaries

```
User (shell stdin)
  │
  ▼ Click arg-parse (untrusted → typed)
CLI wrapper (src/kb/cli.py)
  │  (NO mutation; no pre-validation)
  ▼ function-local import → call MCP tool
MCP tool (src/kb/mcp/browse.py | quality.py)
  │  _strip_control_chars(page_id)          ← CJK/control stripping
  │  _validate_page_id(page_id, check_exists=...)  ← path traversal, length,
  │                                            Windows reserved, resolve-
  │                                            then-relative escape check
  ▼ (page_id now treated as trusted relative path under WIKI_DIR)
Library helpers (kb.review.context.pair_page_with_sources,
                 kb.lint.semantic.build_fidelity_context,
                 kb.compile.linker.build_backlinks,
                 kb.utils.pages.load_all_pages)
  │  second-layer containment: resolve().relative_to(wiki_dir.resolve())
  ▼
Filesystem I/O (read-only)
```

**Key invariant:** the boundary where validation is mandatory is the MCP-tool
entry point, NOT the CLI wrapper. The wrapper's sole job is to forward the arg
and classify the return string.

## 2. Data classification

| Subcommand | Maximum response size | Sensitive content |
|---|---|---|
| `kb read-page <page_id>` | `QUERY_CONTEXT_MAX_CHARS * 4 + 4096` bytes read, truncated to `QUERY_CONTEXT_MAX_CHARS = 80_000` chars (`src/kb/config.py:363`) | Wiki page body (markdown, frontmatter YAML). No secrets expected — repo policy forbids secrets in wiki pages. |
| `kb affected-pages <page_id>` | Bounded by count of backlinks + shared-source pages (both derived from `load_all_pages` output — linearly proportional to wiki size, no caps). | Wiki page IDs only. No raw source content, no frontmatter body. |
| `kb lint-deep <page_id>` | Bounded by page body + all referenced raw sources, inlined with truncation via `_render_sources` + `_truncate_source` (`src/kb/lint/semantic.py:50-60`, min-per-source floor `_MIN_SOURCE_CHARS`). | Wiki page body PLUS raw source text from `raw/papers/*.md`, `raw/articles/*.md`, etc. Raw source text is the largest-surface data class in this cycle. |

**Data-classification rule:** the CLI stdout stream is local-only (single-user
terminal). No additional transport-level confidentiality controls are in scope.
Error strings are sanitized against absolute filesystem paths via
`_sanitize_error_str` → `sanitize_error_text` (`src/kb/utils/sanitize.py:56`).

## 3. Authn/authz

- **Invoker:** single local user. Both CLI and MCP surfaces authenticate by
  process-owner identity; no additional authz layer in scope this cycle.
- **CLI vs MCP equivalence:** the three wrappers are explicitly parity
  surfaces. Operators can invoke either channel; cycle-31 does NOT introduce a
  privilege differential.
- **No-auth rationale:** matches the cycle 27 / cycle 30 parity-cycle precedent
  (`src/kb/cli.py:568-832`) and the project-wide local-first threat model.

## 4. Logging / audit

- **Stdout:** successful page-body / affected-pages / fidelity-context output.
- **Stderr:** validation error strings (via `click.echo(..., err=True)`) and
  verbose tracebacks when `KB_DEBUG=1` or `--verbose` is set (`src/kb/cli.py:44-70`).
- **Log files:** NONE — read-only wrappers do not append to `wiki/log.md` or
  `.data/review_history.json`. This is deliberate; only write surfaces
  (`kb_refine_page`, `kb_create_page`, `kb_ingest`, `kb_refine_sweep`)
  log.
- **PII/secret leak control:** the `_sanitize_error_str` path at
  `src/kb/mcp/app.py:136` routes through `sanitize_error_text` which scrubs
  Windows drive-letter paths, UNC paths, POSIX roots, and exception
  `filename`/`filename2` attributes. Verbose-mode tracebacks bypass this
  sanitizer (`_error_exit` at `src/kb/cli.py:60-70` calls
  `traceback.format_exc()` directly) — acceptable because `KB_DEBUG` is an
  operator-opt-in.

## 5. Threat items

### T1 — Page_id traversal / injection reaching the filesystem without `_validate_page_id`

- **Attack vector:** malicious `page_id` like `"../../etc/passwd"`,
  `"C:\\Windows\\..."`, or `"con.md"` passed through the CLI wrapper and reaches
  `WIKI_DIR / f"{page_id}.md"` without going through the validator.
- **Affected code path:** any CLI wrapper that constructs a filesystem path
  itself instead of forwarding to the MCP tool.
- **Severity:** HIGH (would read arbitrary filesystem content).
- **Mitigation:** wrappers MUST call the MCP tool function directly and MUST
  NOT construct `Path(WIKI_DIR / ...)` themselves. `_validate_page_id`
  (`src/kb/mcp/app.py:250`) is the single checkpoint; it runs inside
  `kb_read_page` (`src/kb/mcp/browse.py:92`), `kb_affected_pages`
  (`src/kb/mcp/quality.py:279`), and `kb_lint_deep`
  (`src/kb/mcp/quality.py:140`). The new wrapper bodies at the forthcoming
  `src/kb/cli.py` `read_page` / `affected_pages` / `lint_deep` commands must
  each contain a `from kb.mcp.browse import kb_read_page` (or `from
  kb.mcp.quality import kb_affected_pages` / `kb_lint_deep`) function-local
  import and a call of the form `output = kb_read_page(page_id)` — with
  `page_id` forwarded verbatim, no re-construction.

### T2 — Unsanitised error strings leaking absolute filesystem paths via `_sanitize_error_str` bypass

- **Attack vector:** a raised exception whose `str()` form contains an absolute
  path is surfaced directly to stderr via `_error_exit` → `_truncate(str(exc))`
  without routing through `_sanitize_error_str`. Local only, but in a
  screen-share / log-aggregator / terminal-recording context this leaks the
  operator's real home directory.
- **Affected code path:** `_error_exit(exc)` at `src/kb/cli.py:60`, which calls
  `_truncate(str(exc))` directly (no sanitizer).
- **Severity:** LOW (local-only context; screen-share scenarios only).
- **Mitigation:** the MCP tool return strings are already sanitized at
  `src/kb/mcp/browse.py:82,139,220,329,348` and
  `src/kb/mcp/quality.py:56,59,99,149,152,184,219,245,290`. The new wrappers
  MUST print the MCP tool's RETURN STRING on the error branch (i.e.,
  `click.echo(output, err=True)` where `output` was already sanitized) and
  ONLY fall through to `_error_exit(exc)` for un-caught exceptions from the
  tool call itself — matching the cycle 27/30 precedent at
  `src/kb/cli.py:639-645, 667-674, 688-695, 721-729, 748-756, 776-784, 796-804,
  823-832`. Verification: for each of the three new wrappers, the error branch
  MUST emit `click.echo(output, err=True); sys.exit(1)` — not
  `_error_exit(Exception(output))`.

### T3 — Error-discriminator misclassification via `_is_mcp_error_response`

- **Attack vector (too narrow):** discriminator only matches `"Error:"` prefix.
  A `kb_read_page` call for a missing page returns `"Page not found: X"` (no
  colon after "Error", no "Error" at all — `src/kb/mcp/browse.py:125`). Exit
  code is 0; piped consumers treat the error text as valid page content.
- **Attack vector (too wide):** discriminator matches any line containing or
  starting with `"Error"`. A legitimate wiki page whose body begins with
  `"# Error Handling in Python"` or `"Errors are..."` is misclassified as an
  error; exit code is 1; piped consumers lose valid output.
- **Affected code path:** the new shared helper `_is_mcp_error_response(output)`
  in `src/kb/cli.py`, consumed by the three new wrappers.
- **Severity:** MEDIUM (silent failure on pipes + false-positive rejection of
  real data).
- **Mitigation:** `_is_mcp_error_response(output)` MUST match EXACTLY three
  prefix shapes against the FIRST LINE ONLY:
  1. `"Error:"` (colon form — `src/kb/mcp/app.py` `_validate_page_id` callers)
  2. `"Error "` (space form — `"Error reviewing "`, `"Error checking fidelity
     for "`, `"Error computing affected pages"` — emitted at
     `src/kb/mcp/quality.py:56,59,149,152,290`)
  3. `"Page not found:"` (emitted at `src/kb/mcp/browse.py:125`)

  Implementation MUST split on the first newline (`output.split("\n", 1)[0]`)
  so a page body whose SECOND line contains the text `"Error: ..."` does not
  misfire. The helper MUST NOT use a substring `in` check — use
  `line.startswith(prefix)` exclusively. Docstring MUST enumerate the three
  prefix shapes with file:line citations so future maintainers do not
  unilaterally widen or narrow the set.

### T4 — Control-char / Unicode injection via `_strip_control_chars` bypass at the CLI boundary

- **Attack vector:** a CLI arg like `"concepts/rag\x1b[31m"` (ANSI escape
  injection) or `"concepts/r‮ag"` (Unicode RLO bidirectional override)
  passed to the wrapper. If the wrapper echoes the raw arg verbatim in a
  formatted error message (e.g., `click.echo(f"Error: {page_id}")`), the
  terminal interprets the escape sequence.
- **Affected code path:** the CLI wrapper's pre-call echo paths. None of the
  three MCP tools accept the raw control chars — `_strip_control_chars` at
  `src/kb/mcp/quality.py:31` and `_CTRL_CHARS_RE` at `src/kb/mcp/app.py:188`
  reject or strip them. But the CLI layer's `_error_exit(exc)` may render
  attacker-supplied bytes unchanged.
- **Severity:** LOW (local terminal only; classic "CVE-fodder-looking but not
  exploitable in single-user local-first posture").
- **Mitigation:** the three wrappers MUST NOT format `page_id` into any CLI-layer
  error string before the MCP tool call. The wrapper body is simply
  `output = kb_<tool>(page_id)` followed by the discriminator check. If the
  wrapper needs to emit a pre-call validation error, it MUST delegate to the
  MCP tool which already runs `_strip_control_chars` (for `kb_lint_deep` at
  `src/kb/mcp/quality.py:139`, `kb_affected_pages` at
  `src/kb/mcp/quality.py:275`; `kb_read_page` relies on `_CTRL_CHARS_RE` in
  `_validate_page_id` at `src/kb/mcp/app.py:262` rejecting rather than
  stripping). Verification: grep the three new wrappers for any
  `f"...{page_id}..."` f-string OUTSIDE the MCP-tool call — expected count:
  zero.

### T5 — Page body output-size DoS (very large pages flooding stdout)

- **Attack vector:** a 500MB wiki page (manual corruption or evidence-trail
  runaway) piped through `kb read-page` overwhelms the operator's terminal /
  shell history buffer.
- **Affected code path:** `kb_read_page` reads with `cap_bytes =
  QUERY_CONTEXT_MAX_CHARS * 4 + 4096` (`src/kb/mcp/browse.py:132`) and caps
  the decoded string at `QUERY_CONTEXT_MAX_CHARS = 80_000` chars
  (`src/kb/mcp/browse.py:150-160`). The cap is inherited by the CLI wrapper
  for free.
- **Severity:** LOW (bounded by existing MCP-tool cap; max ~84KB stdout per
  invocation).
- **Mitigation:** the CLI wrapper MUST call `kb_read_page(page_id)` without
  any `Path.read_text()` fallback or re-read. Verification: grep the
  `read-page` wrapper body for `Path(` / `read_text(` / `open(` — expected
  count: zero. `kb_affected_pages` and `kb_lint_deep` bounds are looser (see
  §2) but both still rely on the MCP tool's internal truncation; wrappers
  MUST not bypass.

### T6 — Boot-lean contract regression (eager imports breaking `kb --version`)

- **Attack vector:** a developer adds a module-level `from kb.mcp.browse import
  kb_read_page` or `from kb.mcp.quality import kb_affected_pages, kb_lint_deep`
  at the top of `src/kb/cli.py`, pulling `frontmatter`, `yaml`,
  `kb.feedback.reliability`, `kb.review.context`, `kb.lint.semantic`,
  `kb.compile.linker`, and `kb.utils.pages` eagerly. This breaks the cycle-23
  AC4/AC5 guarantee that `kb --version` runs before `kb.config` is imported
  (`src/kb/cli.py:7-19`).
- **Affected code path:** module-level imports in `src/kb/cli.py`.
- **Severity:** MEDIUM (breaks operator-facing version probe when config/env
  is broken; regression test would fail but bug would ship without that gate).
- **Mitigation:** each of the three wrappers MUST use a function-local
  `from kb.mcp.<module> import kb_<tool>  # noqa: PLC0415` import INSIDE the
  Click-command function body — matching the cycle 27/30 precedent at
  `src/kb/cli.py:591-595, 636, 665, 686, 720, 747, 775, 795, 823`.
  Verification: AST-scan `src/kb/cli.py` for module-level imports of
  `kb.mcp.browse` or `kb.mcp.quality` — expected count: zero. The existing
  `test_cycle23_mcp_boot_lean.py` battery is a backstop but is scoped to
  `import kb.mcp`, not `import kb.cli`; cycle-31 verification MUST add a
  positive test that the wrapper's import is function-local.

### T7 — MCP-tool behavioural divergence between CLI and MCP invocations

- **Attack vector:** CLI wrapper re-implements `_strip_control_chars`,
  `_validate_page_id`, or the page-existence check, subtly diverging from
  MCP. Example: a wrapper that strips leading/trailing whitespace before
  forwarding would accept `"  concepts/rag  "` on the CLI but reject the
  same input via MCP.
- **Affected code path:** the three new wrapper bodies.
- **Severity:** MEDIUM (silent behavioural drift; breaks parity claim;
  documentation-reality gap).
- **Mitigation:** the three wrappers MUST forward `page_id` VERBATIM from the
  Click arg to the MCP tool call — no `.strip()`, no `.lower()`, no `Path()`
  wrapping. Verification: for each new wrapper, the ONLY transformation
  between Click arg-parse and the MCP call is passing through as a
  positional/keyword argument. Cycle 27 AC1-AC4 and cycle 30 AC2-AC6 pattern
  at `src/kb/cli.py:584-645, 658-695, 713-832` are the reference.

### T8 — Same-class peer drift for `_is_mcp_error_response` (shared helper)

- **Attack vector:** a well-meaning refactor retrofits the new
  `_is_mcp_error_response(output)` helper into existing cycle 27/30 wrappers
  (`search`, `stats`, `list-pages`, `list-sources`, `graph-viz`,
  `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency`).
  Those wrappers were designed around `output.startswith("Error:")`; widening
  their classifier to also match `"Error "` (space form) or `"Page not found:"`
  could reject legitimate output. Example: `kb_stats` returns a line like
  `"Error computing wiki stats: ..."` (`src/kb/mcp/browse.py:348`) which the
  cycle-27 `stats` wrapper correctly handles via `startswith("Error:")`
  (passes because of the colon after "Error"). But `kb_list_pages` could
  legitimately return a header line `"Error rate: 0 pages"` someday, which
  `_is_mcp_error_response`'s space-form matcher would falsely flag.
- **Affected code path:** any retrofit of `_is_mcp_error_response` into
  `src/kb/cli.py:568-832` cycle 27/30 wrappers.
- **Severity:** MEDIUM (regression in shipped wrappers).
- **Mitigation:** `_is_mcp_error_response` is an ADDITIVE helper for the
  THREE new wrappers only. Cycle-27 and cycle-30 wrappers MUST remain on the
  existing `output.startswith("Error:")` check. Verification: the Step-11
  security-verify grep MUST confirm the eight lines at
  `src/kb/cli.py:640, 669, 690, 724, 751, 779, 799, 827` STILL read
  `if output.startswith("Error:"):` verbatim (unchanged) — the shared helper
  is NOT retrofitted.

### T9 — Error-tag shape `"Error[category]: ..."` misclassification

- **Attack vector:** `ERROR_TAG_FORMAT = "Error[{category}]: {message}"` at
  `src/kb/mcp/app.py:17` is currently only emitted by `kb.mcp.core.py` tools
  (ingest / query / capture), not by the three target tools for cycle-31.
  However, if a future refactor adopts `error_tag()` in `kb_read_page`,
  `kb_affected_pages`, or `kb_lint_deep`, the `_is_mcp_error_response`
  discriminator MUST accept `"Error["` as a fourth prefix — otherwise tagged
  errors exit 0 silently.
- **Affected code path:** `_is_mcp_error_response` prefix set; `error_tag` at
  `src/kb/mcp/app.py:97`.
- **Severity:** LOW (future-only; no current emitter in cycle-31 scope).
- **Mitigation:** the docstring of `_is_mcp_error_response` MUST note that the
  tagged form `"Error["` is NOT matched because none of the three target
  tools emit it today, and MUST include a TODO marker pointing at cycle-31
  threat T9 so a future refactor consulting the helper sees the omission.
  Verification: grep the new helper's docstring for the string `"Error["` —
  expected to match with the annotation `"(not emitted by cycle-31 tools)"`.

### T10 — Click `@click.argument("page_id")` type coercion

- **Attack vector:** Click's default `type=str` coercion accepts any stringy
  arg, but on Windows terminals with cp1252 or in piped-stdin contexts with
  mojibake, the arg may arrive as mis-decoded bytes. `_validate_page_id`
  rejects control chars but does not reject U+FFFD (replacement char) or
  other Unicode oddities.
- **Affected code path:** `@click.argument("page_id")` at the three new
  wrappers.
- **Severity:** LOW (validator rejects traversal and length; non-traversal
  Unicode is passed through to the filesystem lookup which fails with
  `"Page not found"`).
- **Mitigation:** no new code; rely on existing `_validate_page_id` + `Page
  not found:` return path. Verification: n/a (no code added for this threat;
  listed for completeness).

---

## 6. Dependency CVE summary

This cycle ships CLI-layer wrappers only; no new Python dependencies are
introduced. `click` and `fastmcp` (via the MCP tools) are already in
`requirements.txt`.

**Expected baseline format (captured separately by the primary):**
`pip-audit` JSON output stored as a Step-2 artifact; Step-11 diff-against-
baseline compares the post-cycle-31 audit to confirm no new advisories enter
via transitive resolution changes (none expected because no new direct deps
are added). If pip-audit reports an advisory against `click` or `fastmcp`
that PRE-EXISTS the cycle-31 diff, it is out of scope (Step 12.5 path, not
Step 11). PR-introduced advisories are in scope at Step 11.

## 7. Step-11 verification checklist

The Step-11 security-verify pass (codex / security reviewer) MUST run the
following checks and emit the expected positive evidence for each.

### T1 — Page_id traversal mitigation

- **Grep:** `Grep(pattern="WIKI_DIR\\s*/\\s*f?\"?\\{?page_id", path="src/kb/cli.py")`
  MUST return zero matches in the three new wrapper bodies. The only path
  construction of the form `WIKI_DIR / f"{page_id}.md"` lives in
  `src/kb/mcp/app.py:283` (the validator) and `src/kb/mcp/browse.py:95,111`
  (the tool) — not the CLI.
- **Read:** `src/kb/cli.py` new `read_page`, `affected_pages`, `lint_deep`
  wrapper bodies MUST each contain a single call of the form
  `kb_read_page(page_id)` / `kb_affected_pages(page_id)` / `kb_lint_deep(page_id)`
  respectively.
- **Expected emit:** "T1 MITIGATED — wrappers forward page_id verbatim to
  validated MCP tools at src/kb/cli.py:<lineno>; no CLI-layer path
  construction present."

### T2 — Error-string sanitisation

- **Grep:** within each new wrapper body in `src/kb/cli.py`, the error branch
  MUST read `click.echo(output, err=True)` where `output` is the MCP tool's
  return string. Pattern: `click\.echo\(output,\s*err=True\)`.
- **Grep:** new wrappers MUST NOT contain `_error_exit(Exception(output))` or
  a manually-constructed exception wrapping the MCP return string.
- **Expected emit:** "T2 MITIGATED — wrapper error branches echo the MCP-tool
  return string directly; sanitisation inherited from
  `_sanitize_error_str` calls at src/kb/mcp/browse.py:82,139 and
  src/kb/mcp/quality.py:56,149,290."

### T3 — Error-discriminator correctness

- **Read:** `src/kb/cli.py` helper `_is_mcp_error_response(output)` docstring
  MUST enumerate the three prefix shapes with file:line citations.
- **Grep:** the helper body MUST contain literal strings `"Error:"`, `"Error "`,
  and `"Page not found:"` — all three shapes.
- **Grep:** the helper body MUST split on the first newline, i.e.
  `split("\n", 1)[0]` or equivalent — the discriminator operates on the FIRST
  LINE ONLY.
- **Test assertion:** the cycle-31 test file MUST include positive-case tests
  for all three shapes (each maps to True) AND negative-case tests for plain
  page bodies whose first line is `"# Page Title"` or starts with `"Error"`
  without a colon/space follower (maps to False).
- **Expected emit:** "T3 MITIGATED — discriminator matches exactly three
  prefix shapes on first line only; both positive and negative cases covered
  by tests at tests/test_cycle31_cli_page_id_wrappers.py."

### T4 — Control-char / Unicode injection

- **Grep:** for each new wrapper body in `src/kb/cli.py`, the pattern
  `f".*\\{page_id\\}.*"` (Click-layer f-string containing page_id) MUST
  return zero matches OUTSIDE the single MCP-tool call line.
- **Expected emit:** "T4 MITIGATED — `page_id` is never interpolated into a
  CLI-layer string before reaching the MCP tool; `_strip_control_chars` +
  `_CTRL_CHARS_RE` at src/kb/mcp/app.py:188 and src/kb/mcp/quality.py:31
  are the single sanitiser."

### T5 — Page body output-size DoS

- **Grep:** in the `read_page` wrapper body, patterns `Path\(`, `read_text`,
  `open\(`, `\.stat\(` MUST return zero matches. The wrapper MUST only call
  `kb_read_page(page_id)` — cap is inherited.
- **Expected emit:** "T5 MITIGATED — `kb read-page` wrapper delegates to
  `kb_read_page` whose cap at src/kb/mcp/browse.py:132,150 bounds output at
  QUERY_CONTEXT_MAX_CHARS=80_000 chars."

### T6 — Boot-lean contract

- **Grep:** `Grep(pattern="^from kb\\.mcp\\.(browse|quality) import",
  path="src/kb/cli.py")` MUST return zero matches at module level (lines 1-32
  of `src/kb/cli.py`, before the first `@click.group()`). All MCP imports MUST
  be inside the Click-command function bodies, annotated with
  `# noqa: PLC0415`.
- **Test assertion:** a new test (or extension of
  `tests/test_cycle23_mcp_boot_lean.py`) MUST subprocess-invoke `kb --version`
  and confirm `kb.mcp.browse` and `kb.mcp.quality` are NOT in `sys.modules`
  afterwards.
- **Expected emit:** "T6 MITIGATED — all three wrappers use function-local
  `from kb.mcp.<module> import ...  # noqa: PLC0415` imports at
  src/kb/cli.py:<lineno>; boot-lean subprocess probe passes."

### T7 — MCP ↔ CLI behavioural parity

- **Grep:** for each new wrapper, the pattern `page_id\.(strip|lower|upper|
  replace|encode)` MUST return zero matches. `page_id` is forwarded verbatim.
- **Grep:** the pattern `Path\(page_id\)` MUST return zero matches.
- **Test assertion:** a parity test MUST invoke the CLI via
  `CliRunner().invoke(cli, ["read-page", "<page_id>"])` AND
  `kb_read_page("<page_id>")` directly, and assert string equality of the two
  outputs on both success and error paths.
- **Expected emit:** "T7 MITIGATED — `page_id` forwarded verbatim; parity
  test at tests/test_cycle31_cli_page_id_wrappers.py asserts byte-identical
  output between CLI and MCP channels."

### T8 — Shared-helper same-class peer-scan (cycle 27 / cycle 30 wrappers unchanged)

- **Grep:** `Grep(pattern="output\\.startswith\\(\"Error:\"\\)",
  path="src/kb/cli.py", output_mode="count")` MUST return **exactly eight**
  matches, located at lines 640, 669, 690, 724, 751, 779, 799, 827 — the
  existing cycle 27/30 wrappers.
- **Grep:** `Grep(pattern="_is_mcp_error_response", path="src/kb/cli.py",
  output_mode="count")` MUST return matches ONLY inside the three new
  wrapper bodies and the helper definition itself (expected: 1 definition +
  3 call sites = 4 total; any higher count indicates retrofit drift).
- **Expected emit:** "T8 MITIGATED — `_is_mcp_error_response` is additive;
  cycle 27/30 wrappers at src/kb/cli.py:640,669,690,724,751,779,799,827
  retain the literal `output.startswith(\"Error:\")` check unchanged; helper
  is invoked from exactly three new call sites."

### T9 — Error-tag shape documentation (`"Error["`)

- **Grep:** within `_is_mcp_error_response`'s docstring, the string
  `"Error["` MUST appear with annotation noting it is NOT emitted by
  cycle-31 tools — pattern like `"Error\\[.*not emitted"` or
  `"Error\\[.*cycle-31"`.
- **Expected emit:** "T9 DOCUMENTED — helper docstring annotates `Error[`
  tagged form as out-of-scope for cycle-31 tools; future `error_tag()`
  adoption in `kb_read_page` / `kb_affected_pages` / `kb_lint_deep` would
  require widening the prefix set and re-running this verification."

### T10 — Click arg type (informational)

- No code check required. Listed for completeness; Python's default string
  decoding + `_validate_page_id`'s control-char regex handle the threat.

### Peer-scan cross-cycle discipline

- **Grep:** `Grep(pattern="_format_search_results", path="src/kb/cli.py")`
  MUST show the cycle-27 AC1b extracted helper is still consumed only by the
  `search` command — NOT by any cycle-31 wrapper. (Sanity that cycle-31
  does not accidentally retrofit cycle-27 plumbing.)
- **Grep:** `Grep(pattern="_audit_token", path="src/kb/cli.py")` MUST continue
  to match only the `rebuild-indexes` command at `src/kb/cli.py:543-558` —
  cycle-29 Q4 compound audit-token is out of scope for cycle-31.
- **Expected emit:** "PEER-SCAN PASSED — no cross-cycle helper retrofit;
  cycle-27 AC1b `_format_search_results` and cycle-29 Q4 `_audit_token`
  remain bound to their original callers."

---

## File written

`D:\Projects\llm-wiki-flywheel\docs\superpowers\decisions\2026-04-25-cycle31-threat-model.md`
