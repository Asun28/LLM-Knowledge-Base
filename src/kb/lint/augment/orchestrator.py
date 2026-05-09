"""Top-level augment orchestration."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Literal

from kb import config
from kb.errors import TierBoundaryError
from kb.lint.augment import collector as collector_mod
from kb.lint.augment import persister as persister_mod
from kb.lint.augment import proposer as proposer_mod
from kb.lint.augment import quality as quality_mod
from kb.lint.augment.fetcher import _url_is_allowed
from kb.utils.io import atomic_text_write
from kb.utils.pages import load_purpose
from kb.utils.text import wrap_wiki_context


def _build_pre_extract_prompt(raw_content: str) -> str:
    """Build the auto_ingest pre-extract scan-tier LLM prompt.

    Cycle 72 AC03: replaces the pre-cycle-72 literal
    ``<untrusted_source>...</untrusted_source>`` XML sentinel pair with
    a ``wrap_wiki_context`` fence (closer-escape + system-prompt-style
    assertion). The orchestrator's auto_ingest path calls this helper at
    the L368 site previously embedded as an inline f-string.

    Defense-in-depth complement to the existing JSON-schema validation
    constraint on the LLM response. The fenced content is the just-fetched
    URL body — fully untrusted; the wrap (a) escapes attacker-planted
    ``</wiki_context>`` closers via ``_escape_wiki_context_close`` and
    (b) prepends the system-prompt-style assertion sentence reminding the
    LLM that fenced content is data not instructions.
    """
    return (
        "Extract structured data from this article per the schema."
        + wrap_wiki_context(raw_content)
    )


# Cycle 73 AC03 — Scan-tier → orchestrate-tier boundary verifier.
#
# Purpose: bound the BLAST RADIUS of cycle-72's prompt-injection
# probability reduction (T4 EscalationOfPrivilege per cycle-73 threat
# model). The cycle-7..72 wrap_wiki_context family REDUCES the
# probability that an LLM follows attacker instructions, but does NOT
# stop a successful injection from propagating malformed JSON into the
# orchestrate-tier persister. This validator re-gates the scan-tier
# output against orchestrate-tier consumption rules — a stricter pass
# than the JSON-schema validation already performed inside
# ``_call_llm_json``.
#
# Default bounds (per design-decision Q3):
#   - max_depth=4    — root + 3 sub-levels covers article-extraction
#                       schemas with 1 level of slack (extraction →
#                       evidence list → claim dict → leaf strings).
#   - max_string_len=4096 — near-neighbour of MAX_ISSUE_DESCRIPTION_LEN
#                            (4000) with 96-char slack for IDs/timestamps.
#
# Anti-spoofing (T5): callers MUST derive ``expected_keys`` from the
# locally-built JSONSchema (e.g. ``frozenset(schema['properties'].keys())``)
# — NEVER from ``scan_output.keys()`` itself. The Step-14 verify step
# greps the call site to confirm.
#
# A future ``max_keys`` bound (R2 F-2 deferred → cycle-74+ BACKLOG) will
# reject objects with > N keys; today's depth+string-len bounds dominate
# the realistic DoS surface.
_TBV_ALLOWED_VALUE_TYPES = (str, int, float, type(None), list, dict)


def _validate_tier_boundary(
    scan_output: object,
    *,
    expected_keys: frozenset[str],
    max_depth: int = 4,
    max_string_len: int = 4096,
) -> dict:
    """Re-gate a scan-tier ``_call_llm_json`` output before orchestrate-tier
    consumption. Raises ``TierBoundaryError`` on any rejection; returns
    ``scan_output`` unchanged on acceptance.

    Rejections (per design-decision §3 + threat-model T4/T5/T6):
        1. Top-level not a ``dict``.
        2. Any key not in ``expected_keys`` (rejects LLM-injected
           ``side_effects`` / ``__proto__`` / etc.).
        3. Any string value longer than ``max_string_len`` (length bound).
        4. Any nested structure deeper than ``max_depth`` (DoS bound).
        5. Any value not in ``_TBV_ALLOWED_VALUE_TYPES`` (rejects custom
           classes if Pydantic / pickle is bypassed). ``bool`` is
           explicitly accepted via the int branch (it's a Python bool
           subclass) — JSON true/false round-trip cleanly.

    Missing keys (subset of ``expected_keys``) are NOT a rejection cause —
    schema-level optional fields are allowed. Downstream consumers use
    ``.get(...)`` to handle missing.
    """
    if not isinstance(scan_output, dict):
        raise TierBoundaryError(
            "tier-boundary verification failed: scan_output is "
            f"{type(scan_output).__name__}, expected dict"
        )

    extra = set(scan_output.keys()) - set(expected_keys)
    if extra:
        raise TierBoundaryError(
            "tier-boundary verification failed: extra key(s) not in "
            f"expected_keys: {sorted(extra)!r}"
        )

    # Walk values for depth + length + type. Depth counts the root dict
    # as level 1 — so max_depth=4 admits root → list → dict → str (4).
    def _walk(value: object, depth: int, key_path: str) -> None:
        if depth > max_depth:
            raise TierBoundaryError(
                "tier-boundary verification failed: nested structure "
                f"deeper than max_depth={max_depth} at {key_path!r}"
            )
        # bool is a subclass of int — handle it via the int branch (no
        # extra check needed; True/False are valid JSON literals).
        if isinstance(value, bool):
            return
        if not isinstance(value, _TBV_ALLOWED_VALUE_TYPES):
            raise TierBoundaryError(
                "tier-boundary verification failed: unsupported value "
                f"type {type(value).__name__} at {key_path!r}"
            )
        if isinstance(value, str):
            if len(value) > max_string_len:
                raise TierBoundaryError(
                    "tier-boundary verification failed: string at "
                    f"{key_path!r} exceeds max_string_len={max_string_len}"
                    f" (len={len(value)})"
                )
        elif isinstance(value, dict):
            for k, v in value.items():
                _walk(v, depth + 1, f"{key_path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                _walk(v, depth + 1, f"{key_path}[{i}]")
        # int / float / None — leaf, no further checks.

    for key, val in scan_output.items():
        _walk(val, 2, key)  # root dict is level 1; values start at 2

    return scan_output


logger = logging.getLogger(__name__)

Mode = Literal["propose", "execute", "auto_ingest"]

_MISSING = object()
_COMPAT_ORIGINALS = {
    "_collect_eligible_stubs": collector_mod._collect_eligible_stubs,
    "_propose_urls": proposer_mod._propose_urls,
    "_wikipedia_fallback": proposer_mod._wikipedia_fallback,
    "_relevance_score": proposer_mod._relevance_score,
    "_format_proposals_md": persister_mod._format_proposals_md,
    "_parse_proposals_md": persister_mod._parse_proposals_md,
    "_save_raw_file": persister_mod._save_raw_file,
    "_mark_page_augmented": persister_mod._mark_page_augmented,
    "_record_attempt": persister_mod._record_attempt,
    "_count_final_stub_outcomes": quality_mod._count_final_stub_outcomes,
    "_resolve_raw_dir": quality_mod._resolve_raw_dir,
    "_record_verdict_gap_callout": quality_mod._record_verdict_gap_callout,
    "_post_ingest_quality": quality_mod._post_ingest_quality,
}


def _package_attr(name: str, fallback: Any) -> Any:
    package = sys.modules.get("kb.lint.augment")
    return getattr(package, name, fallback) if package is not None else fallback


def _compat_symbol(name: str, current: Any) -> Any:
    """Resolve moved helpers through legacy package patches when present."""
    package = sys.modules.get("kb.lint.augment")
    if package is None:
        return current
    package_value = getattr(package, name, _MISSING)
    original = _COMPAT_ORIGINALS.get(name, current)
    if package_value is not _MISSING and package_value is not original:
        return package_value
    return current


def _load_purpose_text(wiki_dir: Path) -> str:
    """Load wiki/purpose.md (first 5000 chars) or empty string on any error."""
    text = load_purpose(wiki_dir)
    return text[:5000] if text else ""


def run_augment(
    *,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    data_dir: Path | None = None,
    mode: Mode = "propose",
    max_gaps: int = 5,
    dry_run: bool = False,
    resume: str | None = None,
) -> dict[str, Any]:
    """Three-gate augment orchestrator."""
    from urllib.parse import urlparse

    import kb
    from kb.lint.augment.manifest import RESUME_COMPLETE_STATES, Manifest
    from kb.lint.augment.rate import RateLimiter
    from kb.mcp.app import _validate_run_id

    resume_manifest: Manifest | None = None
    if resume is not None:
        err = _validate_run_id(resume)
        if err:
            raise ValueError(err)

    wiki_dir = wiki_dir or _package_attr("WIKI_DIR", config.WIKI_DIR)
    raw_dir = _compat_symbol("_resolve_raw_dir", quality_mod._resolve_raw_dir)(wiki_dir, raw_dir)

    effective_data_dir: Path | None
    if data_dir is not None:
        effective_data_dir = Path(data_dir)
    elif wiki_dir != _package_attr("WIKI_DIR", config.WIKI_DIR):
        effective_data_dir = wiki_dir.parent / ".data"
    else:
        effective_data_dir = None

    if not isinstance(max_gaps, int) or max_gaps < 1:
        raise ValueError(f"max_gaps={max_gaps!r} must be a positive integer")
    if max_gaps > config.AUGMENT_FETCH_MAX_CALLS_PER_RUN:
        raise ValueError(
            f"max_gaps={max_gaps} exceeds "
            f"AUGMENT_FETCH_MAX_CALLS_PER_RUN={config.AUGMENT_FETCH_MAX_CALLS_PER_RUN}"
        )

    if resume is not None:
        resume_manifest = Manifest.resume(run_id=resume, data_dir=effective_data_dir)
        if resume_manifest is None:
            raise ValueError(
                f"No incomplete run found for id {resume!r} "
                f"(expected .data/augment-run-{resume}.json with ended_at=null)"
            )
        run_id = resume_manifest.run_id
    else:
        run_id = str(uuid.uuid4())
    proposals: list[dict[str, Any]] = []
    fetches: list[dict[str, Any]] | None = None
    ingests: list[dict[str, Any]] | None = None
    verdicts: list[dict[str, Any]] | None = None
    manifest_path: str | None = None
    manifest: Manifest | None = None
    proposals_path = wiki_dir / "_augment_proposals.md"

    if resume_manifest is not None:
        incomplete = [
            {"stub_id": g["page_id"], "title": g.get("title", ""), "action": "resume"}
            for g in resume_manifest.data.get("gaps", [])
            if g.get("state") not in RESUME_COMPLETE_STATES
        ]
        proposals = incomplete
        eligible = [{"page_id": p["stub_id"], "title": p.get("title", "")} for p in proposals]
    elif mode in ("execute", "auto_ingest"):
        parsed_proposals = _compat_symbol(
            "_parse_proposals_md",
            persister_mod._parse_proposals_md,
        )(proposals_path)
        if parsed_proposals is None:
            early_summary = (
                f"## Augment Summary (run {run_id[:8]}, mode={mode})\n"
                f"- No proposals file found at `{proposals_path}`.\n"
                "- Run `kb lint --augment` first to generate proposals "
                "(gate 1), review them, then re-run with --execute."
            )
            return {
                "run_id": run_id,
                "mode": mode,
                "gaps_examined": 0,
                "gaps_eligible": 0,
                "proposals": [],
                "fetches": None,
                "ingests": None,
                "verdicts": None,
                "manifest_path": None,
                "summary": early_summary,
            }
        proposals = parsed_proposals[:max_gaps]
        eligible = [{"page_id": p["stub_id"], "title": p.get("title", "")} for p in proposals]
    else:
        eligible = _compat_symbol(
            "_collect_eligible_stubs",
            collector_mod._collect_eligible_stubs,
        )(wiki_dir=wiki_dir)[:max_gaps]
        purpose_text = _load_purpose_text(wiki_dir)

        for stub in eligible:
            prop = _compat_symbol("_propose_urls", proposer_mod._propose_urls)(
                stub=stub,
                purpose_text=purpose_text,
            )
            entry: dict[str, Any] = {
                "stub_id": stub["page_id"],
                "title": stub["title"],
                **prop,
            }
            if prop["action"] == "abstain":
                wiki_url = _compat_symbol(
                    "_wikipedia_fallback",
                    proposer_mod._wikipedia_fallback,
                )(page_id=stub["page_id"], title=stub["title"])
                if wiki_url is not None:
                    entry = {
                        "stub_id": stub["page_id"],
                        "title": stub["title"],
                        "action": "propose",
                        "urls": [wiki_url],
                        "rationale": (
                            f"wikipedia fallback (proposer abstained: {prop.get('reason')})"
                        ),
                    }
            proposals.append(entry)

    if mode in ("execute", "auto_ingest") and proposals:
        if dry_run:
            fetches = [{"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals]
        else:
            if resume_manifest is not None:
                manifest = resume_manifest
            else:
                manifest = Manifest.start(
                    run_id=run_id,
                    mode=mode,
                    max_gaps=max_gaps,
                    stubs=[{"page_id": p["stub_id"], "title": p["title"]} for p in proposals],
                    data_dir=effective_data_dir,
                )
            manifest_path = str(manifest.path)
            limiter = RateLimiter(data_dir=effective_data_dir)
            fetches = []
            from kb.lint.fetcher import AugmentFetcher

            with AugmentFetcher(
                allowed_domains=config.get_allowed_domains(),
                version=kb.__version__,
            ) as fetcher:
                for prop in proposals:
                    stub_id = prop["stub_id"]
                    if prop["action"] != "propose":
                        manifest.advance(
                            stub_id, "abstained", payload={"reason": prop.get("reason")}
                        )
                        fetches.append(
                            {
                                "stub_id": stub_id,
                                "status": "abstained",
                                "reason": prop.get("reason"),
                            }
                        )
                        continue

                    fetched_ok = False
                    for url in prop["urls"]:
                        if not _url_is_allowed(url, config.get_allowed_domains()):
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={"reason": f"blocked_by_allowlist: {url}"},
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "blocked_by_allowlist",
                                    "url": url,
                                }
                            )
                            continue
                        parsed_url = urlparse(url)
                        host = (parsed_url.hostname or "").lower()
                        allowed, retry = limiter.acquire(host)
                        if not allowed:
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={"reason": f"rate limited (retry {retry}s)"},
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "rate_limited",
                                    "url": url,
                                    "retry": retry,
                                }
                            )
                            break
                        manifest.advance(stub_id, "proposed", payload={"url": url})
                        result = fetcher.fetch(url)
                        if result.status != "ok":
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "failed",
                                    "url": url,
                                    "reason": result.reason,
                                }
                            )
                            continue
                        manifest.advance(
                            stub_id,
                            "fetched",
                            payload={"url": url, "bytes": result.bytes},
                        )

                        score = _compat_symbol(
                            "_relevance_score",
                            proposer_mod._relevance_score,
                        )(
                            stub_title=prop["title"],
                            extracted_text=result.extracted_markdown or "",
                        )
                        if score < config.AUGMENT_RELEVANCE_THRESHOLD:
                            manifest.advance(
                                stub_id,
                                "failed",
                                payload={
                                    "reason": (
                                        f"relevance {score:.2f} < "
                                        f"{config.AUGMENT_RELEVANCE_THRESHOLD}"
                                    )
                                },
                            )
                            fetches.append(
                                {
                                    "stub_id": stub_id,
                                    "status": "skipped",
                                    "url": url,
                                    "reason": f"relevance {score:.2f} < threshold",
                                }
                            )
                            continue

                        raw_path = _compat_symbol("_save_raw_file", persister_mod._save_raw_file)(
                            raw_dir=raw_dir,
                            stub_id=stub_id,
                            title=prop["title"],
                            url=result.url,
                            run_id=run_id,
                            content=result.extracted_markdown or "",
                            proposer=(
                                "wikipedia-fallback"
                                if "wikipedia fallback" in prop.get("rationale", "")
                                else "llm-scan"
                            ),
                        )
                        manifest.advance(stub_id, "saved", payload={"raw_path": str(raw_path)})
                        fetches.append(
                            {
                                "stub_id": stub_id,
                                "status": "saved",
                                "url": url,
                                "raw_path": str(raw_path),
                                "relevance": score,
                            }
                        )
                        fetched_ok = True
                        break

                    if not fetched_ok and not any(f["stub_id"] == stub_id for f in fetches):
                        manifest.advance(stub_id, "failed", payload={"reason": "all URLs failed"})

            if mode == "execute":
                for f in fetches:
                    if f["status"] == "saved":
                        manifest.advance(f["stub_id"], "done")
                manifest.close()

    if mode == "auto_ingest" and fetches is not None and not dry_run:
        from kb.ingest.extractors import _build_schema_cached
        from kb.ingest.pipeline import ingest_source
        from kb.lint.verdicts import add_verdict

        ingests = []
        verdicts = []
        ingested_stub_ids: set[str] = set()

        for f in fetches:
            stub_id = f["stub_id"]
            if f["status"] != "saved":
                continue
            raw_path = Path(f["raw_path"])

            try:
                schema = _build_schema_cached("article")
                raw_content = raw_path.read_text(encoding="utf-8")
                # Cycle 72 AC03: prompt construction extracted into
                # _build_pre_extract_prompt helper which uses
                # wrap_wiki_context for closer-escape + assertion. Per
                # cycle-23 L2 + cycle-16 L2 — extracting the helper lets
                # AC08 lock-in test reach the production call site
                # without complex run_augment fixture setup.
                extraction = proposer_mod._call_llm_json(
                    _build_pre_extract_prompt(raw_content),
                    tier="scan",
                    schema=schema,
                )
                # Cycle 73 AC03: re-gate scan-tier output before
                # orchestrate-tier consumption. ``expected_keys`` MUST be
                # derived from the LOCAL ``schema`` (built by
                # ``_build_schema_cached``), NOT from the LLM's response —
                # otherwise the validator self-validates (T5 spoofing).
                _validate_tier_boundary(
                    extraction,
                    expected_keys=frozenset(
                        schema.get("properties", {}).keys()
                    ),
                )
            except TierBoundaryError as e:
                # Cycle 73 AC04: forensic-distinct manifest reason.
                # Subclasses ValidationError (so legacy generic
                # ``except ValidationError`` still catches), but the
                # split-catch here records a distinct prefix so
                # investigators can grep ``tier_boundary_rejected:`` for
                # the cross-tier rejection class without false-positives
                # from the generic pre-extract failure path.
                msg = f"tier_boundary_rejected: {e}"
                if manifest is not None:
                    manifest.advance(stub_id, "failed", payload={"reason": msg})
                ingests.append({"stub_id": stub_id, "status": "failed", "reason": msg})
                ingested_stub_ids.add(stub_id)
                continue
            except Exception as e:
                msg = f"pre-extract failed: {type(e).__name__}: {e}"
                if manifest is not None:
                    manifest.advance(stub_id, "failed", payload={"reason": msg})
                ingests.append({"stub_id": stub_id, "status": "failed", "reason": msg})
                ingested_stub_ids.add(stub_id)
                continue

            if manifest is not None:
                manifest.advance(stub_id, "extracted", payload={"keys": list(extraction.keys())})

            try:
                ingest_result = ingest_source(
                    raw_path,
                    source_type="article",
                    extraction=extraction,
                    wiki_dir=wiki_dir,
                    raw_dir=raw_dir,
                    _skip_vector_rebuild=True,
                )
            except Exception as e:
                msg = f"ingest_source failed: {type(e).__name__}: {e}"
                if manifest is not None:
                    manifest.advance(stub_id, "failed", payload={"reason": msg})
                ingests.append({"stub_id": stub_id, "status": "failed", "reason": msg})
                ingested_stub_ids.add(stub_id)
                continue

            if manifest is not None:
                manifest.advance(
                    stub_id,
                    "ingested",
                    payload={
                        "pages_created": ingest_result.get("pages_created", []),
                        "pages_updated": ingest_result.get("pages_updated", []),
                    },
                )

            stub_path = wiki_dir / f"{stub_id}.md"
            if stub_path.exists():
                _compat_symbol("_mark_page_augmented", persister_mod._mark_page_augmented)(
                    stub_path,
                    source_url=f["url"],
                )

            ingests.append(
                {
                    "stub_id": stub_id,
                    "status": "ingested",
                    "pages_created": ingest_result.get("pages_created", []),
                    "pages_updated": ingest_result.get("pages_updated", []),
                }
            )
            ingested_stub_ids.add(stub_id)

            verdict, reason = _compat_symbol(
                "_post_ingest_quality",
                quality_mod._post_ingest_quality,
            )(page_path=stub_path, wiki_dir=wiki_dir)
            add_verdict(
                page_id=stub_id,
                verdict_type="augment",
                verdict=verdict,
                notes=(
                    f"{reason} | augmented from {f['url']} (relevance {f.get('relevance', 0):.2f})"
                ),
                issues=[],
            )
            verdicts.append({"stub_id": stub_id, "verdict": verdict, "reason": reason})

            if verdict == "fail":
                _compat_symbol(
                    "_record_verdict_gap_callout",
                    quality_mod._record_verdict_gap_callout,
                )(stub_path, run_id=run_id, reason=reason)

            if manifest is not None:
                manifest.advance(
                    stub_id,
                    "verdict",
                    payload={"verdict": verdict, "reason": reason},
                )
                manifest.advance(stub_id, "done")

        for prop in proposals:
            stub_id = prop["stub_id"]
            if stub_id in ingested_stub_ids:
                continue
            if prop.get("action") != "propose":
                ingests.append(
                    {
                        "stub_id": stub_id,
                        "status": "skipped",
                        "reason": prop.get("reason", "abstained"),
                    }
                )
            else:
                ingests.append(
                    {
                        "stub_id": stub_id,
                        "status": "failed",
                        "reason": "no successful URL attempts",
                    }
                )

        if manifest is not None:
            manifest.close()

    if mode == "auto_ingest" and dry_run:
        ingests = [{"stub_id": p["stub_id"], "status": "dry_run_skipped"} for p in proposals]

    if not dry_run:
        for stub in eligible:
            _compat_symbol("_record_attempt", persister_mod._record_attempt)(
                wiki_dir / f"{stub['page_id']}.md"
            )

    summary_lines = [f"## Augment Summary (run {run_id[:8]}, mode={mode})"]
    summary_lines.append(f"- Stubs examined: {len(eligible)}")
    summary_lines.append(f"- Proposals: {sum(1 for p in proposals if p['action'] == 'propose')}")
    if fetches is not None:
        saved, skipped, failed = _compat_symbol(
            "_count_final_stub_outcomes",
            quality_mod._count_final_stub_outcomes,
        )(
            proposals=proposals,
            ingests=ingests,
            verdicts=verdicts,
            manifest=manifest,
        )
        summary_lines.append(f"- Saved: {saved}, Skipped: {skipped}, Failed: {failed}")
    if manifest_path:
        summary_lines.append(f"- Manifest: {manifest_path}")

    if mode == "propose" and not dry_run and proposals:
        proposals_md = _compat_symbol(
            "_format_proposals_md",
            persister_mod._format_proposals_md,
        )(proposals, run_id)
        atomic_text_write(proposals_md, proposals_path)
        summary_lines.append(f"- Proposals file: {proposals_path}")

    if mode in ("execute", "auto_ingest") and not dry_run and proposals_path.exists():
        consumed_path = proposals_path.with_name(f"{proposals_path.name}.consumed-{run_id[:8]}")
        try:
            proposals_path.rename(consumed_path)
            summary_lines.append(f"- Proposals consumed: {consumed_path}")
        except OSError as e:
            logger.warning(
                "Failed to rename consumed proposals file %s -> %s: %s",
                proposals_path,
                consumed_path,
                e,
            )

    return {
        "run_id": run_id,
        "mode": mode,
        "gaps_examined": len(eligible),
        "gaps_eligible": len(eligible),
        "proposals": proposals,
        "fetches": fetches,
        "ingests": ingests,
        "verdicts": verdicts,
        "manifest_path": manifest_path,
        "summary": "\n".join(summary_lines),
    }
