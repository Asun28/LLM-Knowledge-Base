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

The package below carries an open advisory with no installable upstream patch and remains in the transitive optional-dependency surface. It is tracked with a re-check cadence and a verification grep confirming the package is not used by `src/kb/` runtime.

| Package | Version | Advisory | Fix? | Narrow role | Verification grep |
|---|---|---|---|---|---|
| `diskcache` | 5.6.3 | [CVE-2025-69872](https://nvd.nist.gov/vuln/detail/CVE-2025-69872) (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE in cache files. | None as of 2026-07-17, cycle-75 re-check (`pip-audit` reports empty `fix_versions`; 5.6.3 is still the latest PyPI release). | Transitive of `trafilatura`'s robots.txt cache. Exploit requires local write access to the cache directory. | `grep -rnE "diskcache\|DiskCache\|FanoutCache" src/kb` → zero direct imports. |

Resolved 2026-05-05: the optional eval harness no longer declares `ragas` or the `litellm` distribution. Dependabot alerts #12 through #15 were closed by removing both package names from `pyproject.toml` `[eval]` and `requirements.txt`. RAGAS had no patched release (`0.4.3` was still latest on PyPI), and patched LiteLLM releases still required `click==8.1.8`, conflicting with this repo's `click==8.3.2` pin. The separate `unclecode-litellm` distribution remains a `crawl4ai` devtime dependency in `requirements.txt`; production `src/kb/` imports of the top-level `litellm` module remain forbidden by `tests/test_security_cve_greps.py`.

Resolved 2026-05-06: CI now upgrades `pip` to `>=26.1` before dependency installs and before the live-environment audit. This removes the prior accepted `CVE-2026-3219` `pip` row and also clears the later `CVE-2026-6357` finding reported against runner-provided `pip 26.0.1`.

The advisory ID above is explicitly listed in `.github/workflows/ci.yml` `pip-audit` step via `--ignore-vuln=` so the CI gate's green-checkmark means "no NEW CVE since cycle 34." Adding any new advisory to the ignore list requires (a) a verification grep, (b) a row in this table, (c) sign-off from the maintainer.

The CI pip-audit step audits the **live installed environment** (no `-r requirements.txt`) — see cycle-34 fix-after-CI-failure-4 in `.github/workflows/ci.yml`. Audit coverage is equivalent because the previous CI step installs every extra (`[dev,formats,augment,hybrid,eval]`), so the live env carries the full pin set. Auditing the live env avoids pip-audit's underlying `pip install --dry-run` step, which trips ResolutionImpossible on `arxiv 2.4.1` ↔ `requests 2.33.0` (cycle-22 L1).

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

*Last reviewed: 2026-07-17 (cycle 75 dep-hygiene re-check: joserfc 1.6.8 + msgpack 1.2.1 + local pip 26.1.2 patched; arxiv 4.0.0 + Crawl4AI 0.9.2 bumps + venv rich sync cleared 3 of 4 pip-check resolver conflicts; diskcache + nltk advisories remain fix-less upstream).*
