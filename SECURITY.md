# Security Policy
<!-- FORMAT GUIDE
Purpose: CVE acceptance policy + disclosure path. Keep this file concise.
- Known Advisories table: add ONE ROW per accepted advisory. Required columns: Package | Version | Advisory | Fix? | Narrow role | Verification grep.
  - "Narrow role" must describe why the vulnerable code path is not reachable from src/kb/ runtime.
  - "Verification grep" must be a runnable command returning zero hits in src/kb/.
  - New rows require: (a) verification grep, (b) sign-off from maintainer, (c) --ignore-vuln= entry in ci.yml pip-audit step.
- Resolved advisories: add a brief prose note below the table; delete the table row.
- Update "Last reviewed:" date each cycle when CVEs are re-checked.
-->

## Vulnerability Reporting

We take security issues seriously. Please report suspected vulnerabilities through one of these channels:

1. **GitHub Security Advisory** (preferred): open a private advisory at <https://github.com/Asun28/llm-wiki-flywheel/security/advisories/new>. This keeps the report private until a fix is ready.
2. **Email fallback**: contact the project maintainer at the email listed on the GitHub profile page (<https://github.com/Asun28>). Include "llm-wiki-flywheel security" in the subject line.

Please do NOT open a public GitHub issue for security reports. Public issues may give attackers a head start before a fix lands.

We aim to acknowledge reports within 72 hours and to land a fix or documented mitigation within 30 days for HIGH/CRITICAL severities.

## Known Advisories

**The accepted-advisory table is currently EMPTY** — as of cycle 76 (2026-07-17) no installed package carries an accepted open advisory, and the CI `pip-audit` step runs with zero `--ignore-vuln=` exceptions. When a new advisory must be accepted, restore a row per the FORMAT GUIDE above.

| Package | Version | Advisory | Fix? | Narrow role | Verification grep |
|---|---|---|---|---|---|

Resolved 2026-07-17 (cycle 76): the `diskcache` 5.6.3 pickle-deserialization RCE row (CVE-2025-69872 / GHSA-w8v5-vhqr-4h9v) is gone because `diskcache` left the dependency tree entirely. Its ONLY reverse-dependency was the unused `dspy` pin (`pip show diskcache` → Required-by: dspy; zero `dspy`/`diskcache` imports repo-wide); the former "transitive of trafilatura's robots.txt cache" rationale was stale — `trafilatura` 2.0.0 neither declares nor imports it. Cycle 76 removed `dspy` and its six orphan-only transitive pins (`diskcache`, `gepa`, `optuna`, `asyncer`, `cloudpickle`, `json_repair`) from `requirements.txt` and the venv, dropped the last `--ignore-vuln=CVE-2025-69872` flag from CI, and made the CI `pip check` step strict (the dspy→litellm gap was the last tolerated resolver conflict). `diskcache` imports in `src/kb/` remain forbidden by the CVE-banned-imports guard test.

Resolved 2026-05-05: the optional eval harness no longer declares `ragas` or the `litellm` distribution. Dependabot alerts #12 through #15 were closed by removing both package names from `pyproject.toml` `[eval]` and `requirements.txt`. RAGAS had no patched release (`0.4.3` was still latest on PyPI), and patched LiteLLM releases still required `click==8.1.8`, conflicting with this repo's `click==8.3.2` pin. The separate `unclecode-litellm` distribution remains a `crawl4ai` devtime dependency in `requirements.txt`; production `src/kb/` imports of the top-level `litellm` module remain forbidden by `tests/test_security_cve_greps.py`.

Resolved 2026-05-06: CI now upgrades `pip` to `>=26.1` before dependency installs and before the live-environment audit. This removes the prior accepted `CVE-2026-3219` `pip` row and also clears the later `CVE-2026-6357` finding reported against runner-provided `pip 26.0.1`.

The `--ignore-vuln=` list in the `.github/workflows/ci.yml` `pip-audit` step mirrors this table 1:1 (set-parity enforced by `tests/test_cycle36_ci_hardening.py`) — both are empty since cycle 76, so the CI gate's green-checkmark means "no CVE on any installed package, no exceptions." Adding any new advisory to the ignore list requires (a) a verification grep, (b) a row in this table, (c) sign-off from the maintainer.

The CI pip-audit step audits the **live installed environment** (no `-r requirements.txt`) — see cycle-34 fix-after-CI-failure-4 in `.github/workflows/ci.yml`. Audit coverage is equivalent because the previous CI step installs every extra (`[dev,formats,augment,hybrid,eval]`), so the live env carries the full pin set. Auditing the live env avoids pip-audit's underlying `pip install --dry-run` resolution step (the historical trigger was the since-resolved `arxiv 2.4.1` ↔ `requests 2.33.0` conflict — cycle-22 L1; the live-env form remains the safer default).

## Re-check Cadence

The CVE acceptance list is re-evaluated every cycle:

- **Step 2 baseline (per cycle):** capture current Dependabot alerts + `pip-audit` snapshot to `.data/cycle-<N>/`. Surfaces NEW advisories or upstream fixes.
- **Step 11 PR-introduced CVE diff:** compare branch's `pip-audit` JSON output against the Step-2 baseline. Any advisory ID in branch but not in baseline blocks the PR until pinned to a patched version (or accepted into this table with documentation).
- **Step 11.5 existing-CVE opportunistic patch:** for any alert whose `first_patched_version` is non-null, bump the pin in `requirements.txt`, install, re-run pytest + ruff, commit as `fix(deps): patch <CVE>`.
- **Step 15 late-arrival warn:** post-merge diff against the Step-11.5 fresh read. New advisories that landed during the cycle become a BACKLOG entry for the next cycle's Step 2 baseline.

This cadence is documented in the project's feature-dev workflow at `~/.claude/skills/feature-dev/SKILL.md` Steps 2, 11, 11.5, and 15.

## Scope

This policy covers:

- The Python package `kb` (importable as `kb`, `kb.cli`, `kb.mcp`, etc.) and its CLI / MCP surface.
- The `tests/` test suite — though tests intentionally hit security boundaries to verify they hold.

This policy does NOT cover:

- The wiki content (`wiki/`) or raw sources (`raw/`) — those are user-owned data outside the scope of this codebase.
- Third-party LLM providers (Anthropic, OpenAI, etc.) reached via the CLI backend — report to the provider directly.
- Optional `[hybrid]` / `[augment]` / `[eval]` extras — vulnerabilities in those packages are tracked above only when relevant to default-install users; report extras-only vulnerabilities to the upstream package directly.

---

*Last reviewed: 2026-07-17 (cycle 76: dspy + 6 orphan pins removed → diskcache CVE-2025-69872 eliminated from the tree, accepted-advisory table now EMPTY, CI pip-audit runs exception-free, CI pip check strict. Cycle 75 earlier the same day: joserfc 1.6.8 + msgpack 1.2.1 + local pip 26.1.2 patched; arxiv 4.0.0 + Crawl4AI 0.9.2 + venv rich sync. Remaining fix-less upstream advisory: nltk GHSA-p4gq-832x-fm9v — transitive, not installed in CI, tracked in BACKLOG.)*
