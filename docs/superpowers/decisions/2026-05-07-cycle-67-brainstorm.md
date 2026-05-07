# Cycle 67 — Brainstorming

**Date:** 2026-05-07
**Pipeline:** dev-mimo-opus, Step 3 (Opus main)
**Predecessors:** `2026-05-07-cycle-67-requirements.md` (Step 1), threat model dispatched (Step 2 in background)

This doc enumerates design alternatives for ACs whose requirements doc lists multiple plausible implementations. The design eval at Step 4 (R1 Opus + R2 DeepSeek) will pick.

For ACs with one obvious implementation (AC02 AST guard test, AC08 conftest meta-test, AC09 paired snapshot, AC10/AC11 CI greps, AC13 README section, AC15 secrets scrub tests), the requirements doc's spec is final — not re-explored here.

---

## AC01 — `MODEL_TIERS` legacy dict → call-time view

### Approach A — Dict subclass with overridden `__getitem__`

```python
class _ModelTiersView(dict):
    def __getitem__(self, tier: str) -> str:
        return get_model_tier(tier)
    def __init__(self) -> None:
        super().__init__(_DEFAULT_MODEL_TIERS)
```

**Pros:** drop-in for `MODEL_TIERS["scan"]`; iter / `.get` / `in` work via dict super.
**Cons:** seeded values are stale (would diverge from `__getitem__` if someone iterated and dereferenced); subclassing dict is fragile (CPython `dict.__getitem__` fast path can bypass `__getitem__` in C-level callers).

### Approach B — Plain class with only `__getitem__` plus collections.abc.Mapping

```python
class _ModelTiersView:
    __slots__ = ()
    def __getitem__(self, tier: str) -> str:
        return get_model_tier(tier)
    def __contains__(self, tier: str) -> bool:
        return tier in _DEFAULT_MODEL_TIERS
    def __iter__(self):
        return iter(_DEFAULT_MODEL_TIERS)
    def __len__(self):
        return len(_DEFAULT_MODEL_TIERS)
    def get(self, tier: str, default=None):
        try:
            return self[tier]
        except (ValueError, KeyError):
            return default

MODEL_TIERS = _ModelTiersView()
```

**Pros:** every access route hits `__getitem__` (no C-level fast path); explicit minimal contract.
**Cons:** strict `isinstance(MODEL_TIERS, dict)` callers break — but grep confirmed there are none today.

### Approach C — Module-level `__getattr__` on `kb.config`

```python
def __getattr__(name: str):
    if name == "MODEL_TIERS":
        return {tier: get_model_tier(tier) for tier in _DEFAULT_MODEL_TIERS}
    raise AttributeError(...)
```

**Pros:** every `kb.config.MODEL_TIERS` access rebuilds the dict fresh.
**Cons:** breaks `from kb.config import MODEL_TIERS` (cached at import time); incompatible with existing test imports.

### Recommendation: **Approach B**

Strict subset of dict interface, no inheritance fragility, every read path env-dynamic. Tests using `MODEL_TIERS["scan"]` keep working. Grep confirms no `isinstance(MODEL_TIERS, dict)` callers. Step 4 R2 DeepSeek will adversarially probe iter / `__contains__` paths.

---

## AC03 — Chunked stdout cap with terminate-at-limit

### Approach A — `Popen` + threaded reader

Two daemon threads (stdout + stderr) accumulate via `read(64*1024)` until `MAX_CLI_STDOUT_BYTES` cap. Main thread calls `proc.communicate(input=..., timeout=...)` then waits on threads.

**Pros:** explicit cap, cross-platform, established pattern.
**Cons:** Subtle thread-join semantics on `terminate()`; Windows `terminate()` is `TerminateProcess` (no SIGTERM grace).

### Approach B — `Popen` + selectors loop in main thread

Use `selectors.DefaultSelector()` to multiplex stdout+stderr reads in main thread.

**Pros:** no threads — simpler reasoning.
**Cons:** Windows `selectors` does NOT support pipes (only sockets). Falls back to busy-poll. Blocks the call site (no concurrent stderr drain → potential stderr-pipe deadlock if backend writes >64K to stderr).

### Approach C — `asyncio.create_subprocess_exec`

**Pros:** modern, clean cancellation.
**Cons:** changes the sync `call_cli` signature; ripples into every caller. Out of scope for cycle 67's "preserve trust boundary" framing.

### Recommendation: **Approach A**

Cross-platform, no API ripple. Acknowledge Windows `terminate()` ≠ SIGTERM in the docstring. Use `proc.terminate()` then `proc.wait(timeout=2)` and on `TimeoutExpired`, `proc.kill()`. Document the 64KB chunk + small overrun as acceptable residual risk in the threat model.

---

## AC07 — Duplicate-slug allowlist externalization

### Approach A — `wiki/_lint.yml`

YAML in the wiki tree alongside content. Operator-friendly.

**Pros:** lives with wiki content; per-wiki config natural; YAML is human-friendly for nested allowlists.
**Cons:** PyYAML dep needed (project already has it via Anthropic SDK transitives — verify at Step 7).

### Approach B — `.data/lint_allowlist.json`

JSON in `.data/` (project-level state).

**Pros:** stdlib json, no new dep; matches existing `.data/` convention.
**Cons:** less human-friendly; `.data/` may be gitignored; separates lint config from wiki.

### Approach C — `wiki/_lint.toml`

TOML using stdlib `tomllib` (Python 3.11+).

**Pros:** stdlib parser; aligns with `pyproject.toml`.
**Cons:** less natural for list-of-pairs structure than YAML.

### Recommendation: **Approach A** (`wiki/_lint.yml`)

PyYAML is already a transitive dep. Keeping config with content matches `wiki/log.md`, `wiki/contradictions.md` patterns. JSON is acceptable fallback if YAML proves problematic.

Format:
```yaml
duplicate_slug_allowlist:
  - ["concepts/bot", "concepts/llm"]
  - ["entities/openai", "entities/openclaw"]
  - ["entities/logql", "entities/promql"]
```

---

## AC12 — Docstring audit script — Args/Returns/Raises detection

### Approach A — Simple regex per section header

`re.search(r"^\s*Args:", doc, re.M)`. Three boolean checks.

**Pros:** stdlib, fast, simple.
**Cons:** false-negatives on indented docstrings; silent acceptance of malformed sections.

### Approach B — `docstring_parser` library

```python
from docstring_parser import parse
doc = parse(fn.__doc__ or "")
has_args = bool(doc.params)
has_returns = bool(doc.returns)
has_raises = bool(doc.raises)
```

**Pros:** robust parsing; doesn't false-negative on indentation.
**Cons:** new dependency; pin needed; pip-audit follow-up.

### Approach C — Stdlib `inspect.getdoc` + `ast`-walk for `raise` to gate `Raises:` requirement

Hybrid: simple regex for section headers, plus `ast.walk(ast.parse(inspect.getsource(fn)))` to determine if function has any `raise` statement that would trigger `Raises:` requirement.

**Pros:** stdlib only; conditional `Raises:` check matches docstring_parser's intent.
**Cons:** regex still fragile.

### Recommendation: **Approach C**

Stdlib only (no new dep). Combine regex for headers (sufficient for Google style which is the project convention) + `ast.walk` to detect `raise` statements outside `try` blocks (so `Raises:` is only mandatory when functions actually raise).

If audit produces N>0 offenders today (likely), AC12 ships in WARNING-ONLY CI mode for cycle 67; hard-fail deferred to a future cycle (BACKLOG entry created at Step 17). Threshold ratchet pattern.

---

## AC14 — `docs/reference/INDEX.md` consistency check

### Approach A — Pure script that walks `docs/reference/*.md` + parses INDEX.md + CLAUDE.md table

```python
fs_files = {p.name for p in Path("docs/reference").glob("*.md") if p.name != "INDEX.md"}
index_files = parse_index_md(...)
claude_files = parse_claude_table(...)
missing_in_index = fs_files - index_files
missing_in_claude = fs_files - claude_files
```

**Pros:** simple, fast, exact-match.
**Cons:** brittle to CLAUDE.md table format changes — regex `\[.*?\]\(docs/reference/(.*?\.md)\)` would miss alternative link styles.

### Approach B — Markdown AST parsing via `markdown-it-py`

Walk the AST, collect all `link` tokens with target prefix `docs/reference/`.

**Pros:** robust to formatting variations; commonmark-spec-correct.
**Cons:** new dep (markdown-it-py).

### Recommendation: **Approach A** (regex)

CLAUDE.md table format is stable. Regex `\[[^\]]*\]\(docs/reference/([^)]+\.md)\)` is sufficient. If format ever changes, AC14 script's regex can be updated in the same commit.

---

## Cross-AC: import-time vs call-time env reads

ACs touching env vars: AC01 (MODEL_TIERS), AC04 (KB_STRICT_PUBLISH), AC06 (KB_DISABLE_VECTORS).

**Cycle-19 L2 rule**: any module-top `read_text()` or `os.environ.get(...)` whose path/value derives from an env var MUST be wrapped in a lazy `_get_X()` helper. Apply uniformly:

- AC01: `_ModelTiersView.__getitem__` reads via `get_model_tier()` which already reads at call time
- AC04: `compile_wiki` reads `os.environ.get("KB_STRICT_PUBLISH", "")` at the publish call site, not at module top
- AC06: hybrid dispatch reads `os.environ.get("KB_DISABLE_VECTORS", "")` at query time

Step 14 verifier checklist (in threat model) MUST grep each new env var for module-top capture vs call-time read.

---

## Out-of-scope brainstorming (deferred)

- AC04's interaction with `compile_wiki(mode="full")` — does strict-publish behavior change for full vs incremental compile? Default: same behavior either way (env-controlled, not mode-controlled). Step 7 plan locks.
- AC07's interaction with `kb_lint --augment auto_ingest` mode — auto-ingest triggers a synthetic wiki tree without `_lint.yml`. Default: fall through to config defaults (already specified).
- AC03's interaction with `gemini` backend's `--prompt` argv — refactor preserves the same arg construction and `_check_no_secrets_on_argv` call; only the `subprocess.run` → `Popen` path changes.

---

## Step 4 design eval routing

R1 (Opus 4.7 main session via `plan-eng-review` skill): focus on AC03 (Popen refactor risk surface), AC07 (file-format choice + lint config layering), AC12 (warning-only CI mode trade-off).

R2 (`deepseek-rescue` @ `deepseek-v4-pro`): focus on AC01 (proxy class fragility, dict subclass vs plain class), AC05 (sqlite_vec error chain), AC11 (CI grep false-positive risk on legitimate uses of `sk-ant-dummy` substring).

Cross-vendor diversity preserved (Opus + DeepSeek). Step 5 decision gate (Opus subagent) consolidates.
