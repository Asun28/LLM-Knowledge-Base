"""Cycle 86 — validation & ordering correctness.

Covers four runtime ACs traced to BACKLOG.md, plus the doc-anchor for a fifth:

  AC01  `lint/checks/evidence_resolvable.py` — every file-shaped `source:`
        frontmatter entry must resolve to a real file under `raw/`.
  AC02  `_validate_tier_boundary(allowed_values=...)` — closed action
        vocabulary enforced AT the scan/orchestrate boundary.
  AC03  `ingest/pipeline.py` — human `wiki/log.md` success line moves after
        the manifest commit; a post-commit interrupt no longer emits
        `stage="failure"`.
  AC04  `utils/io.py` — parent-directory fsync so the rename is durable.
  AC05  a BACKLOG deletion with no runtime surface; pinned by the doc
        assertions at the bottom of this file.

Revert-sensitivity (C16-L2 / C24-L4): every test reaches the real production
call site with inputs that DIVERGE old and new behaviour. Tests that would
still pass against a revert are worse than none, so the AC03 ordering tests
assert relative ORDER rather than presence, and the AC04 tests spy the
production helper rather than exercising `os.fsync` in isolation.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

import pytest

from kb.errors import TierBoundaryError, ValidationError, ValueDomainError
from kb.ingest import pipeline as pipeline_mod
from kb.lint import runner as runner_mod
from kb.lint.augment import proposer as proposer_mod
from kb.lint.augment.tier_boundary import _validate_tier_boundary
from kb.lint.checks import evidence_resolvable as evidence_mod
from kb.utils import io as io_mod

# ==========================================================================
# Shared helpers
# ==========================================================================


def _write_page(wiki_dir: Path, page_id: str, sources: list[str] | str | None) -> Path:
    """Write a minimal wiki page carrying the given `source:` frontmatter."""
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if sources is None:
        fm = ""
    elif isinstance(sources, str):
        fm = f'source: "{sources}"\n'
    else:
        fm = "source:\n" + "".join(f'  - "{s}"\n' for s in sources)
    path.write_text(
        f'---\ntitle: "{page_id}"\n{fm}type: concept\n---\n\nBody text.\n',
        encoding="utf-8",
    )
    return path


def _stub_extraction() -> dict:
    return {
        "title": "Cycle 86 Ordering Source",
        "summary": "Small test source used by cycle 86 ordering tests.",
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_points": ["Trigger the ingest path."],
    }


def _seed_raw(tmp_kb_env: Path, slug: str) -> Path:
    raw = tmp_kb_env / "raw" / "articles" / f"{slug}.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(f"# {slug}\n\nBody.\n", encoding="utf-8")
    return raw


def _ingest(tmp_kb_env: Path, raw: Path) -> dict:
    return pipeline_mod.ingest_source(
        raw,
        source_type="article",
        extraction=_stub_extraction(),
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
        _skip_vector_rebuild=True,
    )


def _jsonl_stages(tmp_kb_env: Path) -> list[str]:
    """Every `stage` value recorded in `.data/ingest_log.jsonl`, in order."""
    path = tmp_kb_env / ".data" / "ingest_log.jsonl"
    if not path.is_file():
        return []
    stages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            stages.append(json.loads(line)["stage"])
    return stages


def _wiki_log_text(tmp_kb_env: Path) -> str:
    path = tmp_kb_env / "wiki" / "log.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# ==========================================================================
# AC01 — evidence-resolvability check
# ==========================================================================


def test_resolvable_ref_produces_no_finding(tmp_path):
    """A source ref pointing at a real file under raw/ is clean."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    (raw / "articles").mkdir(parents=True)
    (raw / "articles" / "real.md").write_text("source body", encoding="utf-8")
    page = _write_page(wiki, "concepts/good", ["raw/articles/real.md"])

    assert evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page]) == []


def test_url_refs_are_skipped_not_flagged(tmp_path):
    """URL-sourced pages are a supported shape — flagging them would make the
    check unusable on every augmented page (design Q2)."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    page = _write_page(
        wiki,
        "concepts/urls",
        ["https://example.com/post", "HTTP://Example.COM/other"],
    )

    assert evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page]) == []


def test_dangling_ref_is_reported_as_warning_naming_page_and_ref(tmp_path):
    """The AC's core contract: name the page AND the dangling ref.

    Severity is `warning`, not `error` — a raw source can legitimately be
    pruned after ingest, so this must not flip `kb lint`'s exit code
    repo-wide (design DESIGN-AMEND).
    """
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    page = _write_page(wiki, "concepts/dangling", ["raw/articles/deleted.md"])

    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page])

    assert len(issues) == 1
    (issue,) = issues
    assert issue["check"] == "evidence_unresolvable"
    assert issue["severity"] == "warning"
    assert issue["page"] == "concepts/dangling.md"
    assert issue["source"] == "raw/articles/deleted.md"
    # Both identifiers must appear in the human message, not just the fields.
    assert "raw/articles/deleted.md" in issue["message"]
    assert "concepts/dangling.md" in issue["message"]


def test_string_valued_source_frontmatter_is_handled(tmp_path):
    """`source:` may be a bare string rather than a list."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    page = _write_page(wiki, "concepts/scalar", "raw/articles/missing.md")

    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page])

    assert [i["source"] for i in issues] == ["raw/articles/missing.md"]


@pytest.mark.parametrize(
    "escaping_ref",
    [
        "raw/../../../etc/shadow",
        "../../secrets.txt",
        "raw/../../outside.md",
    ],
)
def test_escaping_ref_is_error_severity(tmp_path, escaping_ref):
    """A ref leaving raw/ is never legitimate — corruption or injection."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    page = _write_page(wiki, "concepts/escape", [escaping_ref])

    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page])

    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["source"] == escaping_ref


def test_escaping_ref_is_never_stat_ed(tmp_path, monkeypatch):
    """T1 — the check must not become a filesystem-existence oracle.

    Reaching `.is_file()` on an out-of-tree ref would let anyone who can
    influence frontmatter probe arbitrary host paths through lint output.
    This spies the real `Path.is_file` rather than asserting on source text
    (C11-L2: no source-scan tests).
    """
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    page = _write_page(wiki, "concepts/probe", ["raw/../../../etc/shadow"])

    probed: list[str] = []
    real_is_file = Path.is_file

    def _spy_is_file(self):
        probed.append(str(self))
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", _spy_is_file)
    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page])

    assert len(issues) == 1
    assert not any("shadow" in p for p in probed), (
        f"out-of-tree ref was stat'd — T1 oracle regression. Probed: {probed}"
    )


@pytest.mark.parametrize(
    "hostile_ref",
    [
        r"\\attacker.invalid\share\probe",  # UNC — SMB/DNS traffic on resolve
        "//attacker.invalid/share/probe",
        "C:/Windows/System32/config/SAM",  # drive-absolute
        "/etc/shadow",  # POSIX absolute
        r"raw\\\\attacker.invalid\share\x",  # UNC smuggled behind the raw/ strip
    ],
)
def test_hostile_ref_is_rejected_without_resolving_it(tmp_path, monkeypatch, hostile_ref):
    """BLOCKER (Codex review): `Path.resolve()` is itself filesystem access.

    The first version checked containment only AFTER resolving, so a UNC ref
    could initiate SMB/DNS/authentication traffic during resolution — the
    probe IS the payload, and avoiding `.is_file()` afterwards is too late.
    These refs must be rejected on the string alone, so `resolve` is never
    reached.
    """
    resolved: list[str] = []
    real_resolve = Path.resolve

    def _spy_resolve(self, *a, **k):
        resolved.append(str(self))
        return real_resolve(self, *a, **k)

    monkeypatch.setattr(Path, "resolve", _spy_resolve)

    assert evidence_mod._resolve_evidence_ref(hostile_ref, tmp_path) is None
    assert not any("attacker.invalid" in p or "System32" in p for p in resolved), (
        f"hostile ref was resolved before the containment check: {resolved}"
    )


def test_per_page_ref_cap_truncates_and_reports(tmp_path):
    """T2 — a pathological page cannot dominate the lint run, and the
    truncation is reported rather than silent."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    over = evidence_mod._EVIDENCE_REFS_PER_PAGE_CAP + 25
    page = _write_page(wiki, "concepts/flood", [f"raw/a/{i}.md" for i in range(over)])

    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[page])

    truncations = [i for i in issues if i["check"] == "evidence_refs_truncated"]
    unresolvable = [i for i in issues if i["check"] == "evidence_unresolvable"]
    assert len(truncations) == 1
    assert str(over) in truncations[0]["message"]
    assert len(unresolvable) == evidence_mod._EVIDENCE_REFS_PER_PAGE_CAP


def test_check_is_registered_in_the_lint_runner(tmp_path):
    """A helper not wired into the orchestrator is orphan code — the cycle-3
    PR-review MAJOR. Assert `kb lint` surfaces the finding end-to-end, not
    just that the function works in isolation."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    (wiki / "concepts").mkdir(parents=True)
    raw.mkdir(parents=True)
    _write_page(wiki, "concepts/orphaned-evidence", ["raw/articles/gone.md"])

    report = runner_mod.run_all_checks(wiki, raw)

    assert "evidence_resolvable" in [c["name"] for c in report["checks_run"]]
    assert any(i["check"] == "evidence_unresolvable" for i in report["issues"]), (
        "check ran but its findings never reached the report"
    )


def test_unreadable_page_does_not_abort_the_scan(tmp_path):
    """One malformed page must not take down the whole lint run."""
    wiki, raw = tmp_path / "wiki", tmp_path / "raw"
    raw.mkdir(parents=True)
    good = _write_page(wiki, "concepts/good", ["raw/articles/gone.md"])
    missing = wiki / "concepts" / "does-not-exist.md"

    issues = evidence_mod.check_evidence_resolvable(wiki, raw, pages=[missing, good])

    assert [i["source"] for i in issues] == ["raw/articles/gone.md"]


# ==========================================================================
# AC02 — closed action vocabulary at the tier boundary
# ==========================================================================

_EXPECTED = frozenset(proposer_mod._PROPOSER_SCHEMA["properties"].keys())
_REQUIRED = frozenset(proposer_mod._PROPOSER_SCHEMA["required"])
_VOCAB = {"action": proposer_mod._ACTION_VOCABULARY}


def test_vocabulary_is_derived_from_the_local_schema():
    """T4/T5 anti-spoofing — the enum comes from LOCAL schema text, never
    from model output. If someone later hardcodes the literal, this fails."""
    assert proposer_mod._ACTION_VOCABULARY == frozenset(
        proposer_mod._PROPOSER_SCHEMA["properties"]["action"]["enum"]
    )
    assert proposer_mod._ACTION_VOCABULARY == frozenset({"propose", "abstain"})


@pytest.mark.parametrize("action", ["propose", "abstain"])
def test_in_vocabulary_actions_pass_the_boundary(action):
    out = _validate_tier_boundary(
        {"action": action},
        expected_keys=_EXPECTED,
        required_keys=_REQUIRED,
        allowed_values=_VOCAB,
    )
    assert out == {"action": action}


@pytest.mark.parametrize(
    "invented",
    ["exfiltrate", "delete_all", "resume", "PROPOSE", "", "propose "],
)
def test_invented_action_is_rejected_at_the_boundary(invented):
    """T3 — the point of the AC. `PROPOSE` and `propose ` are rejected too:
    vocabulary membership is exact, not fuzzy."""
    with pytest.raises(ValueDomainError) as excinfo:
        _validate_tier_boundary(
            {"action": invented},
            expected_keys=_EXPECTED,
            required_keys=_REQUIRED,
            allowed_values=_VOCAB,
        )
    assert "not in the permitted vocabulary" in str(excinfo.value)


@pytest.mark.parametrize("hostile", [["propose"], {"a": 1}, {"propose"}])
def test_unhashable_action_value_is_rejected_not_crashed(hostile):
    """`value in frozenset` raises TypeError on an unhashable value rather
    than returning False. An enum field arriving as a list is itself
    out-of-vocabulary, so it must reject — not leak a TypeError."""
    with pytest.raises(ValueDomainError):
        _validate_tier_boundary(
            {"action": hostile}, expected_keys=_EXPECTED, allowed_values=_VOCAB
        )


def test_value_domain_error_is_catchable_as_its_ancestors():
    """Back-compat: every legacy `except TierBoundaryError` / `except
    ValidationError` site must still catch the new subclass."""
    payload = {"action": "invented"}
    kwargs = {"expected_keys": _EXPECTED, "allowed_values": _VOCAB}

    with pytest.raises(TierBoundaryError):
        _validate_tier_boundary(payload, **kwargs)
    with pytest.raises(ValidationError):
        _validate_tier_boundary(payload, **kwargs)
    assert issubclass(ValueDomainError, TierBoundaryError)


def test_absent_key_is_not_a_vocabulary_rejection():
    """Absence is `required_keys`' job. Conflating the two would silently
    make every optional enum field mandatory."""
    out = _validate_tier_boundary(
        {"urls": []}, expected_keys=_EXPECTED, allowed_values=_VOCAB
    )
    assert out == {"urls": []}


def test_omitting_allowed_values_is_a_no_op():
    """Back-compat for the call sites that pass no vocabulary."""
    out = _validate_tier_boundary({"action": "anything"}, expected_keys=_EXPECTED)
    assert out == {"action": "anything"}


def test_key_domain_rejection_still_outranks_value_domain():
    """An unexpected key must be reported as an unexpected key, not
    misattributed to the vocabulary gate."""
    with pytest.raises(TierBoundaryError) as excinfo:
        _validate_tier_boundary(
            {"action": "invented", "side_effects": "rm -rf"},
            expected_keys=_EXPECTED,
            allowed_values=_VOCAB,
        )
    assert "extra key" in str(excinfo.value)
    assert not isinstance(excinfo.value, ValueDomainError)


def test_propose_urls_fails_closed_with_distinct_reason(monkeypatch):
    """End-to-end at the real call site: an invented action must abstain with
    the forensically distinct `action_not_in_vocabulary:` prefix.

    This reaches `_propose_urls` (not just the validator), so it also covers
    removal of the hand-rolled `if action != "propose"` branch — CONDITION 3.
    """
    monkeypatch.setattr(
        proposer_mod,
        "_call_llm_json",
        lambda *a, **k: {"action": "exfiltrate", "urls": ["https://evil.test/x"]},
    )

    result = proposer_mod._propose_urls(stub={"page_id": "concepts/x"}, purpose_text="")

    assert result["action"] == "abstain"
    assert result["reason"].startswith("action_not_in_vocabulary:")
    # Distinct from the pre-existing shape-rejection reason.
    assert not result["reason"].startswith("tier_boundary_rejected:")
    assert "urls" not in result


def test_propose_urls_shape_rejection_keeps_its_own_reason(monkeypatch):
    """The split-catch must not collapse: a SHAPE violation still reports
    `tier_boundary_rejected:`, not the new vocabulary reason."""
    monkeypatch.setattr(
        proposer_mod,
        "_call_llm_json",
        lambda *a, **k: {"action": "propose", "side_effects": "rm -rf /"},
    )

    result = proposer_mod._propose_urls(stub={"page_id": "concepts/x"}, purpose_text="")

    assert result["action"] == "abstain"
    assert result["reason"].startswith("tier_boundary_rejected:")


def test_propose_urls_still_accepts_a_valid_proposal(monkeypatch):
    """The gate must not break the happy path."""
    monkeypatch.setattr(
        proposer_mod,
        "_call_llm_json",
        lambda *a, **k: {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/Test"],
            "rationale": "authoritative",
        },
    )
    monkeypatch.setattr(proposer_mod, "_url_is_allowed", lambda *a, **k: True)

    result = proposer_mod._propose_urls(stub={"page_id": "concepts/x"}, purpose_text="")

    assert result["action"] == "propose"
    assert result["urls"] == ["https://en.wikipedia.org/wiki/Test"]


@pytest.mark.xfail(
    strict=True, reason="AC02: an invented action must never survive _propose_urls"
)
def test_invented_action_surviving_the_proposer_is_a_regression(monkeypatch):
    """xfail-strict negative (CONDITION 2).

    Goes through `_propose_urls` rather than calling the validator directly.
    The first version of this test supplied `allowed_values` itself, so
    removing that argument from the production call site would not have
    affected it — it proved the validator works, not that the caller uses it
    (Codex review NIT). Driving the real entry point means dropping
    `allowed_values` at `proposer.py` makes this xfail start PASSING, and
    strict mode turns that into a suite failure.
    """
    monkeypatch.setattr(
        proposer_mod,
        "_call_llm_json",
        lambda *a, **k: {"action": "exfiltrate", "urls": ["https://evil.test/x"]},
    )
    monkeypatch.setattr(proposer_mod, "_url_is_allowed", lambda *a, **k: True)

    result = proposer_mod._propose_urls(stub={"page_id": "concepts/x"}, purpose_text="")

    # Only reachable if the invented action was NOT rejected.
    assert result["action"] == "propose"


# ==========================================================================
# AC03 — ingest log ordering + post-commit interruption
# ==========================================================================


def test_human_log_is_appended_after_the_manifest_commit(tmp_kb_env, monkeypatch):
    """The ordering contract itself.

    Pre-cycle-86 the log was appended at step 7 of `_run_ingest_body`, i.e.
    BEFORE `_commit_ingest_manifest`. Reverting flips these two markers and
    fails the assertion — this asserts relative ORDER, not presence (C24-L4:
    presence assertions are revert-tolerant).
    """
    order: list[str] = []
    real_commit = pipeline_mod._commit_ingest_manifest
    real_log = pipeline_mod._append_ingest_success_log

    def _spy_commit(*a, **k):
        order.append("commit")
        return real_commit(*a, **k)

    def _spy_log(*a, **k):
        order.append("human_log")
        return real_log(*a, **k)

    monkeypatch.setattr(pipeline_mod, "_commit_ingest_manifest", _spy_commit)
    monkeypatch.setattr(pipeline_mod, "_append_ingest_success_log", _spy_log)

    _ingest(tmp_kb_env, _seed_raw(tmp_kb_env, "log-ordering"))

    assert order == ["commit", "human_log"], (
        f"human log must follow the manifest commit, got {order}"
    )


def test_failed_commit_leaves_no_success_line_in_wiki_log(tmp_kb_env, monkeypatch):
    """T5 — the defect this AC closes.

    A commit failure used to leave `wiki/log.md` asserting a successful
    ingest the manifest never recorded, so the human audit trail contradicted
    the machine state.
    """
    monkeypatch.setattr(
        pipeline_mod,
        "_commit_ingest_manifest",
        lambda *a, **k: (_ for _ in ()).throw(OSError("simulated commit failure")),
    )

    raw = _seed_raw(tmp_kb_env, "commit-fails")
    with pytest.raises(OSError):
        _ingest(tmp_kb_env, raw)

    assert "Ingested" not in _wiki_log_text(tmp_kb_env)
    assert _jsonl_stages(tmp_kb_env)[-1] == "failure"


def test_successful_ingest_still_writes_the_human_log_line(tmp_kb_env):
    """The move must not drop the line — a silent regression would be worse
    than the ordering bug it fixes."""
    raw = _seed_raw(tmp_kb_env, "log-still-written")
    _ingest(tmp_kb_env, raw)

    log = _wiki_log_text(tmp_kb_env)
    assert "Ingested" in log
    assert "raw/articles/log-still-written.md" in log
    assert "[req=" in log


def test_post_commit_interrupt_does_not_emit_a_failure_row(tmp_kb_env, monkeypatch):
    """T5, second half — an interrupt AFTER the commit must not be recorded
    as a failed ingest, because the pages and the manifest entry are durable.

    Pre-cycle-86 every exception reaching the handler emitted
    `stage="failure"`, producing a correlation record that actively
    contradicted durable state.
    """
    from kb.compile import compiler as compiler_mod

    monkeypatch.setattr(
        pipeline_mod,
        "_append_ingest_success_log",
        lambda **k: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    raw = _seed_raw(tmp_kb_env, "post-commit-interrupt")
    with pytest.raises(KeyboardInterrupt):
        _ingest(tmp_kb_env, raw)

    stages = _jsonl_stages(tmp_kb_env)
    assert "failure" not in stages, f"post-commit interrupt emitted failure: {stages}"
    assert "success" in stages
    # And the commit really did land, so the ingest is not re-selected.
    assert "raw/articles/post-commit-interrupt.md" in compiler_mod.load_manifest()


def test_post_commit_interrupt_before_success_row_still_emits_success(
    tmp_kb_env, monkeypatch
):
    """Covers the `if not success_emitted` retry: an interrupt landing in the
    window between the commit and the success emission must still leave
    exactly one terminal row for the request_id."""
    real_emit = pipeline_mod._emit_ingest_jsonl
    fired = {"n": 0}

    def _interrupt_first_success(stage, *a, **k):
        if stage == "success" and fired["n"] == 0:
            fired["n"] += 1
            raise KeyboardInterrupt()
        return real_emit(stage, *a, **k)

    monkeypatch.setattr(pipeline_mod, "_emit_ingest_jsonl", _interrupt_first_success)

    raw = _seed_raw(tmp_kb_env, "interrupt-window")
    with pytest.raises(KeyboardInterrupt):
        _ingest(tmp_kb_env, raw)

    stages = _jsonl_stages(tmp_kb_env)
    assert "failure" not in stages
    assert stages.count("success") == 1


def test_pre_commit_failure_still_emits_a_failure_row(tmp_kb_env, monkeypatch):
    """The `committed` flag must not suppress GENUINE failures — that would
    trade one audit defect for a worse one."""
    monkeypatch.setattr(
        pipeline_mod,
        "_run_ingest_body",
        lambda **k: (_ for _ in ()).throw(RuntimeError("body blew up")),
    )

    raw = _seed_raw(tmp_kb_env, "pre-commit-failure")
    with pytest.raises(Exception):
        _ingest(tmp_kb_env, raw)

    assert "failure" in _jsonl_stages(tmp_kb_env)
    assert "Ingested" not in _wiki_log_text(tmp_kb_env)


def test_run_ingest_body_no_longer_emits_the_success_audit_line(
    tmp_kb_env, monkeypatch
):
    """C18-L2 — the caller owns the telemetry envelope. `_run_ingest_body` is
    a pure worker; if a future edit re-adds the emission there, the ordering
    guarantee silently breaks again."""
    logged: list[str] = []
    real_append = pipeline_mod.append_wiki_log

    def _spy_append(action, message, *a, **k):
        logged.append(message)
        return real_append(action, message, *a, **k)

    monkeypatch.setattr(pipeline_mod, "append_wiki_log", _spy_append)
    monkeypatch.setattr(
        pipeline_mod,
        "_commit_ingest_manifest",
        lambda *a, **k: (_ for _ in ()).throw(OSError("stop before the tail")),
    )

    with pytest.raises(OSError):
        _ingest(tmp_kb_env, _seed_raw(tmp_kb_env, "worker-purity"))

    assert not any("Ingested" in m for m in logged), (
        f"_run_ingest_body emitted a success audit line: {logged}"
    )


# ==========================================================================
# AC04 — parent-directory fsync
# ==========================================================================


def test_atomic_json_write_fsyncs_the_parent_directory(tmp_path, monkeypatch):
    """Spies the production helper at the real call site rather than
    exercising `os.fsync` standalone (C16-L2).

    Cycle 87 AC01 pins the platform explicitly. The parent-dir fsync is the
    POSIX barrier only — Windows now takes the `MoveFileExW` write-through path
    and never calls this helper. Before, this passed on Windows only because the
    helper was still *called* there as a no-op, which is the accident that let
    the Windows durability gap survive cycle 86.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)
    seen: list[Path] = []
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", lambda d: seen.append(Path(d)))

    target = tmp_path / "nested" / "manifest.json"
    io_mod.atomic_json_write({"raw/articles/example.md": "a" * 64}, target)

    assert seen == [target.parent]
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "raw/articles/example.md": "a" * 64
    }


def test_atomic_text_write_fsyncs_the_parent_directory(tmp_path, monkeypatch):
    """Design Q4 — the same-class peer. This is the higher-traffic surface:
    every wiki page and evidence-trail append lands here.

    Cycle 87 AC01 — POSIX branch, see the JSON peer above.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)
    seen: list[Path] = []
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", lambda d: seen.append(Path(d)))

    target = tmp_path / "nested" / "page.md"
    io_mod.atomic_text_write("page body\n", target)

    assert seen == [target.parent]
    assert target.read_text(encoding="utf-8") == "page body\n"


def test_dir_fsync_runs_after_the_rename_not_before(tmp_path, monkeypatch):
    """Ordering matters: fsync-ing the directory before the rename would
    flush the wrong state and provide no durability at all.

    Cycle 87 AC01 — the rename primitive is `os.replace` inside
    `durable_replace`, not `Path.replace`; spying the old one would observe
    nothing and assert a one-element order vacuously.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)
    order: list[str] = []
    real_replace = io_mod.os.replace

    def _spy_replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(io_mod.os, "replace", _spy_replace)
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", lambda d: order.append("dir_fsync"))

    io_mod.atomic_json_write({"k": "v"}, tmp_path / "out.json")

    assert order == ["replace", "dir_fsync"]


def test_fsync_parent_dir_swallows_errors_rather_than_failing_the_write(tmp_path):
    """T7 — the durability barrier must not convert working writes into hard
    failures on filesystems that reject fsync on a directory handle. The REAL
    helper is exercised here, against a directory that does not exist."""
    io_mod._fsync_parent_dir(tmp_path / "no-such-dir")  # must not raise


def test_text_path_dir_fsync_also_runs_after_its_rename(tmp_path, monkeypatch):
    """The ordering test above covers the JSON path only. Without this, moving
    the TEXT path's fsync before its rename would leave the suite green while
    defeating durability on the higher-traffic surface (Codex review MINOR).
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)
    order: list[str] = []
    real_replace = io_mod.os.replace

    def _spy_replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(io_mod.os, "replace", _spy_replace)
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", lambda d: order.append("dir_fsync"))

    io_mod.atomic_text_write("body\n", tmp_path / "page.md")

    assert order == ["replace", "dir_fsync"]


def test_helper_tolerates_an_unsupported_fsync(tmp_path, monkeypatch):
    """T7, direct: an `EINVAL`-class refusal (the filesystem does not support
    fsync on a directory handle) is tolerated.

    Called directly rather than through `atomic_json_write`, because a blanket
    `os.fsync` patch would also hit `_flush_and_fsync` — which is REQUIRED to
    raise, and whose failure is a different contract. That confusion is what
    CI caught on ubuntu-latest.
    """

    def _unsupported(fd):
        raise OSError(errno.EINVAL, "fsync not supported on this directory")

    monkeypatch.setattr(os, "fsync", _unsupported)

    io_mod._fsync_parent_dir(tmp_path)  # must not raise


@pytest.mark.skipif(os.name == "nt", reason="helper is a no-op on Windows")
def test_helper_raises_on_a_genuine_storage_failure(tmp_path, monkeypatch):
    """A real `EIO` must NOT be swallowed (Codex review MAJOR).

    Silence would be read as durability: `_commit_ingest_manifest` would
    declare the ingest committed while a power loss can still revert the
    manifest, with success telemetry already on disk saying otherwise.
    """

    def _eio(fd):
        raise OSError(errno.EIO, "device failure")

    monkeypatch.setattr(os, "fsync", _eio)

    with pytest.raises(OSError):
        io_mod._fsync_parent_dir(tmp_path)


def test_write_still_succeeds_when_dir_fsync_is_unavailable(tmp_path, monkeypatch):
    """T7 end-to-end: a filesystem that rejects fsync on a DIRECTORY handle
    must not break writes that work today.

    The patch fails only directory descriptors. Failing every fsync would
    take out `_flush_and_fsync` too and prove nothing about the directory
    barrier — that mistake is what CI caught on ubuntu-latest, since the
    content fsync raised before the code under test was ever reached.
    """
    real_fsync = os.fsync

    def _fail_only_on_directories(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            # errno must be set, not just described in the message: after the
            # MAJOR-4 fix the helper classifies on `e.errno`, and an errno-less
            # OSError is (correctly) treated as a genuine storage failure
            # rather than an unsupported call. CI caught this.
            raise OSError(errno.EINVAL, "fsync not supported on this directory")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _fail_only_on_directories)
    target = tmp_path / "resilient.json"

    io_mod.atomic_json_write({"k": "v"}, target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v"}


@pytest.mark.parametrize(
    ("raised", "expect_raise"),
    [
        (OSError(errno.EINVAL, "unsupported"), False),
        (OSError(errno.ENOTSUP, "unsupported"), False),
        (OSError(errno.EPERM, "not permitted"), False),
        (OSError(errno.EIO, "device failure"), True),
        (OSError(errno.ENOSPC, "no space"), True),
        (OSError("no errno at all"), True),
    ],
)
def test_fsync_errno_classification_is_platform_independent(
    tmp_path, monkeypatch, raised, expect_raise
):
    """Pin MAJOR-4's tolerate-vs-raise split WITHOUT depending on the host OS.

    The real POSIX/Windows branches are guarded by skipif, so on Windows the
    classifier was never executed and two CI rounds were burned discovering
    that in ubuntu instead. This drives the branch directly by faking the
    POSIX path, so the rule is enforced wherever the suite runs.

    An errno-less OSError is expected to RAISE: unknown cause is treated as a
    genuine failure, which is the conservative direction for a durability
    barrier.
    """
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "open", lambda *a, **k: 4242)
    monkeypatch.setattr(os, "close", lambda fd: None)

    def _raise(fd):
        raise raised

    monkeypatch.setattr(os, "fsync", _raise)

    if expect_raise:
        with pytest.raises(OSError):
            io_mod._fsync_parent_dir(tmp_path)
    else:
        io_mod._fsync_parent_dir(tmp_path)


def test_fsync_close_error_does_not_mask_the_durability_verdict(tmp_path, monkeypatch):
    """A failing `os.close` must not turn a SUCCESSFUL fsync into an error —
    the durability question was already answered by then."""
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "open", lambda *a, **k: 4242)
    monkeypatch.setattr(os, "fsync", lambda fd: None)

    def _bad_close(fd):
        raise OSError(errno.EIO, "close failed")

    monkeypatch.setattr(os, "close", _bad_close)

    io_mod._fsync_parent_dir(tmp_path)  # must not raise


@pytest.mark.skipif(os.name != "nt", reason="Windows no-op branch")
def test_fsync_parent_dir_is_a_no_op_on_windows(tmp_path, monkeypatch):
    """NTFS has no O_DIRECTORY and `os.open` on a directory raises there;
    rename durability comes from MoveFileEx instead."""
    called: list[int] = []
    monkeypatch.setattr(os, "fsync", lambda fd: called.append(fd))

    io_mod._fsync_parent_dir(tmp_path)

    assert called == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX fsync path")
def test_fsync_parent_dir_actually_fsyncs_on_posix(tmp_path, monkeypatch):
    """The Windows no-op must not silently disable the POSIX path."""
    called: list[int] = []
    real_fsync = os.fsync

    def _spy(fd):
        called.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _spy)
    io_mod._fsync_parent_dir(tmp_path)

    assert len(called) == 1


# ==========================================================================
# AC05 — backlog hygiene: the stale load_manifest entry is gone
# ==========================================================================


def _repo_root() -> Path:
    """Walk up from this file until BACKLOG.md appears — the cycle-23 AC2 /
    cycle-73 hygiene pattern. The `real_project_root` fixture is not usable
    here because it requires the `--use-real-paths` opt-out flag.
    """
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        if (ancestor / "BACKLOG.md").exists():
            return ancestor
    raise AssertionError("BACKLOG.md not found in any ancestor of tests/")


def test_backlog_no_longer_claims_compiler_read_sites_are_unguarded():
    """AC05 pins the DELETION, not just the behaviour behind it.

    The behavioural test below proves cycle 84's guard works, but it would
    keep passing if someone restored the stale backlog entry — so on its own
    it does not pin AC05 at all (Codex review MINOR). This asserts the claim
    text is actually gone.
    """
    backlog = (_repo_root() / "BACKLOG.md").read_text(encoding="utf-8")

    assert "the `compiler.py` read sites remain unguarded" not in backlog
    assert "`load_manifest` has no value type check" not in backlog


def test_corrupt_manifest_value_does_not_kill_the_compile_scan(tmp_path, monkeypatch):
    """The evidence behind AC05's backlog deletion, asserted behaviourally.

    Cycle 84 added the `isinstance(stored, str)` guard at compiler.py:185, so
    a hand-edited `.data/hashes.json` holding a non-string value must classify
    the source as changed (self-healing) instead of raising AttributeError and
    taking down every other source in the scan.
    """
    from kb.compile import compiler as compiler_mod

    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True)
    (raw_dir / "articles" / "corrupt-row.md").write_text("# body\n", encoding="utf-8")

    corrupt = {"raw/articles/corrupt-row.md": 42, "raw/articles/other.md": ["a"]}
    monkeypatch.setattr(compiler_mod, "load_manifest", lambda *a, **k: dict(corrupt))

    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=raw_dir)

    selected = {p.name for p in list(new_sources) + list(changed_sources)}
    assert "corrupt-row.md" in selected
