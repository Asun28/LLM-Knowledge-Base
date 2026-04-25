# Security Policy

## Vulnerability Reporting

We take security issues seriously. Please report suspected vulnerabilities through one of these channels:

1. **GitHub Security Advisory** (preferred): open a private advisory at <https://github.com/Asun28/llm-wiki-flywheel/security/advisories/new>. This keeps the report private until a fix is ready.
2. **Email fallback**: contact the project maintainer at the email listed on the GitHub profile page (<https://github.com/Asun28>). Include "llm-wiki-flywheel security" in the subject line.

Please do NOT open a public GitHub issue for security reports. Public issues may give attackers a head start before a fix lands.

We aim to acknowledge reports within 72 hours and to land a fix or documented mitigation within 30 days for HIGH/CRITICAL severities.

## Known Advisories

The four packages below carry open advisories with no installable upstream patch (or patches blocked by dependency-resolver constraints). Each is tracked with a re-check cadence and a verification grep confirming the package is not used by `src/kb/` runtime.

| Package | Version | Advisory | Fix? | Narrow role | Verification grep |
|---|---|---|---|---|---|
| `diskcache` | 5.6.3 | [CVE-2025-69872](https://nvd.nist.gov/vuln/detail/CVE-2025-69872) (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE in cache files. | None as of 2026-04-25 (`pip-audit` reports empty `fix_versions`). | Transitive of `trafilatura`'s robots.txt cache. Exploit requires local write access to the cache directory. | `grep -rnE "diskcache\|DiskCache\|FanoutCache" src/kb` → zero direct imports. |
| `litellm` | 1.83.0 | [GHSA-xqmj-j6mv-4862](https://github.com/advisories/GHSA-xqmj-j6mv-4862) (high) + GHSA-r75f-5x8p-qvmc (critical): LiteLLM Proxy template-injection + arbitrary code execution inside proxy process. | Available at `1.83.7` but BLOCKED by `litellm 1.83.7`'s `click<8.2` transitive constraint conflicting with our `click==8.3.2` pin (cycle 31/32 CLI wrappers depend on click ≥8.2). | Dev-eval-only dependency (ragas evaluation harness). We never start LiteLLM Proxy mode, so the vulnerable proxy endpoints are unreachable. | `grep -rnE "import litellm\|from litellm" src/kb` → zero runtime imports. |
| `pip` | 26.0.1 | [CVE-2026-3219](https://nvd.nist.gov/vuln/detail/CVE-2026-3219) (GHSA-58qw-9mgm-455v): pip handles concatenated tar+ZIP files as ZIP regardless of filename, enabling confusing installation behaviour. | None as of 2026-04-25. | TOOLING, not runtime. Advisory affects `pip install` of adversarial tar+zip payloads which requires local shell access. Production `kb` runtime never shells out to `pip`. | N/A (pip is universally bundled with Python). |
| `ragas` | 0.4.3 | [CVE-2026-6587](https://nvd.nist.gov/vuln/detail/CVE-2026-6587) (GHSA-95ww-475f-pr4f): SSRF in `_try_process_local_file` / `_try_process_url` of `ragas.metrics.collections.multi_modal_faithfulness.util`. | None as of 2026-04-25 (vendor did not respond to disclosure). | Dev-eval-only dependency. An attacker would need local Python access to run `python -c "from ragas..."` themselves — no remote reach. | `grep -rnE "ragas\|Ragas" src/kb` → zero runtime imports. |

These four advisory IDs are explicitly listed in `.github/workflows/ci.yml` `pip-audit` step via `--ignore-vuln=` so the CI gate's green-checkmark means "no NEW CVE since cycle 34." Adding any new advisory to the ignore list requires (a) a verification grep, (b) a row in this table, (c) sign-off from the maintainer.

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

*Last reviewed: 2026-04-25 (cycle 34).*
