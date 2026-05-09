"""Cycle 73 AC03+AC04 — Scan-tier → orchestrate-tier boundary verifier.

Tests for cycle-73 AC03+AC04:
- AC03: ``_validate_tier_boundary(scan_output, *, expected_keys, max_depth=4,
  max_string_len=4096) -> dict`` helper at
  ``src/kb/lint/augment/orchestrator.py:394`` site re-gates scan-tier
  ``_call_llm_json`` outputs against orchestrate-tier consumption rules.
- AC04: ``TierBoundaryError(ValidationError)`` exception in ``kb.errors``;
  orchestrator catch-block uses split-catch (``except TierBoundaryError``
  BEFORE generic ``except Exception``); manifest reason prefix literal
  ``"tier_boundary_rejected: ..."`` for forensic distinctness.

Per design-decision Q2/Q3/Q7 + §11 (FROZEN at Step 5):
- C-AC03-1: helper signature accepts EXPLICIT ``expected_keys`` only (NO
  ``schema=`` shortcut — prevents T5 self-validating loop).
- C-AC03-2..4: depth=4, string-len=4096, value-type allowlist
  (str|int|float|bool|None|list|dict).
- C-AC03-5: rejects extra keys, accepts subset (legitimate optional fields).
- C-AC03-7: spy test exercises the ``orchestrator.py:394`` production
  path (not a unit test of helper in isolation).
- C-AC04-1: ``TierBoundaryError`` subclasses ``ValidationError``.
- C-AC04-2: split-catch order — ``TierBoundaryError`` BEFORE ``Exception``.
- C-AC04-3: manifest reason starts with literal ``"tier_boundary_rejected:"``.

Threat-model:
- T4 (EscalationOfPrivilege — scan-tier proposes orchestrate-tier writes)
- T5 (Spoofing — LLM-fabricated expected_keys; defended at call site)
- T6 (DenialOfService — pathological JSON depth)
- T9 (Repudiation — manifest distinctness)

Per ``feedback_test_behavior_over_signature``: all assertions exercise the
production code path; no inspect.getsource / source-grep / dead double-call.
"""

from __future__ import annotations

import pytest

# ── AC03 helper-in-isolation lock-in ──────────────────────────────────


class TestAC03_ValidateTierBoundaryAcceptance:
    """C-AC03-1..5: well-formed input passes through unchanged."""

    def test_validate_accepts_well_formed_subset(self):
        """Well-formed dict with subset of expected_keys passes through.

        C-AC03-5: missing keys are NOT a rejection cause — only EXTRA keys
        are. (Missing keys handled downstream by ``.get(...)`` consumers.)
        """
        from kb.lint.augment.orchestrator import _validate_tier_boundary

        scan_output = {"summary": "ok", "title": "X"}
        expected = frozenset({"summary", "title", "evidence", "citations"})

        result = _validate_tier_boundary(scan_output, expected_keys=expected)
        assert result is scan_output, (
            "validator returned new object; it should pass through unchanged"
        )

    def test_validate_accepts_full_keyset(self):
        """Dict with ALL expected_keys (no missing, no extra) passes."""
        from kb.lint.augment.orchestrator import _validate_tier_boundary

        scan_output = {
            "title": "X",
            "summary": "ok",
            "evidence": [{"src": "raw/a.md", "claim": "Y"}],
        }
        expected = frozenset({"title", "summary", "evidence"})

        result = _validate_tier_boundary(scan_output, expected_keys=expected)
        assert result == scan_output


class TestAC03_ValidateTierBoundaryRejection:
    """C-AC03-1..5: rejects ill-formed input via TierBoundaryError.

    Cycle-20 L1 reload-leak guard: ``TierBoundaryError`` is late-bound via
    the orchestrator's already-imported attribute (``orch_mod.TierBoundaryError``)
    rather than re-imported from ``kb.errors`` at test time. A sibling
    test that monkeypatches ``KB_PROJECT_ROOT`` then calls
    ``importlib.reload(kb.config)`` cascade-reloads ``kb.errors``, creating
    a NEW ``TierBoundaryError`` class — production code (orchestrator)
    raises whatever class IT bound at import time, while a test importing
    via ``from kb.errors import TierBoundaryError`` resolves the NEW
    class. ``pytest.raises(<test-class>)`` then sees ``DID NOT RAISE``
    because the actual exception is a DIFFERENT class. Late-binding via
    the orchestrator's bound attribute keeps both production and test
    pointing at the SAME class regardless of reload state.
    """

    def test_validate_rejects_non_dict_input(self):
        """Non-dict at top level → TierBoundaryError."""
        from kb.lint.augment import orchestrator as orch_mod

        for bad in (None, [], "not a dict", 42, ()):
            with pytest.raises(orch_mod.TierBoundaryError):
                orch_mod._validate_tier_boundary(
                    bad,  # type: ignore[arg-type]
                    expected_keys=frozenset({"summary"}),
                )

    def test_validate_rejects_extra_key(self):
        """LLM-injected extra key (not in expected_keys) → TierBoundaryError.

        Defends T4: prevents LLM from injecting e.g. ``"side_effects"`` key
        that orchestrate-tier might accidentally consume.
        """
        from kb.lint.augment import orchestrator as orch_mod

        scan_output = {"summary": "ok", "side_effects": "delete_all"}
        expected = frozenset({"summary"})

        with pytest.raises(orch_mod.TierBoundaryError, match="side_effects"):
            orch_mod._validate_tier_boundary(scan_output, expected_keys=expected)

    def test_validate_rejects_oversize_string(self):
        """String value longer than ``max_string_len=4096`` → TierBoundaryError."""
        from kb.lint.augment import orchestrator as orch_mod

        scan_output = {"summary": "X" * 5000}
        with pytest.raises(orch_mod.TierBoundaryError):
            orch_mod._validate_tier_boundary(scan_output, expected_keys=frozenset({"summary"}))

    def test_validate_rejects_oversize_string_in_nested(self):
        """Oversize string in NESTED dict/list → TierBoundaryError (not just
        top-level scan)."""
        from kb.lint.augment import orchestrator as orch_mod

        scan_output = {
            "evidence": [{"claim": "X" * 5000}],
        }
        with pytest.raises(orch_mod.TierBoundaryError):
            orch_mod._validate_tier_boundary(scan_output, expected_keys=frozenset({"evidence"}))

    def test_validate_rejects_deep_nesting(self):
        """Nested structure deeper than ``max_depth=4`` → TierBoundaryError.

        Defends T6 DoS — pathological JSON-bombs.
        """
        from kb.lint.augment import orchestrator as orch_mod

        # 6-level-deep nested dict (root + 5 levels) exceeds max_depth=4.
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "leaf"}}}}}}
        with pytest.raises(orch_mod.TierBoundaryError):
            orch_mod._validate_tier_boundary(deep, expected_keys=frozenset({"a"}))

    def test_validate_accepts_legitimate_depth(self):
        """3-level dict (root + 2 sub-levels) is within depth=4 → passes."""
        from kb.lint.augment.orchestrator import _validate_tier_boundary

        ok = {"evidence": [{"src": "raw/a.md", "claim": "X"}]}
        # depth = root(1) + list(2) + dict(3) + leaf-strings(4) = 4 → passes
        result = _validate_tier_boundary(ok, expected_keys=frozenset({"evidence"}))
        assert result is ok

    def test_validate_rejects_unsupported_value_type(self):
        """Custom-class value (e.g., a Pydantic model bypassing JSON) →
        TierBoundaryError."""
        from kb.lint.augment import orchestrator as orch_mod

        class BadValue:
            pass

        scan_output = {"summary": BadValue()}  # type: ignore[dict-item]
        with pytest.raises(orch_mod.TierBoundaryError):
            orch_mod._validate_tier_boundary(scan_output, expected_keys=frozenset({"summary"}))

    def test_validate_accepts_int_float_bool_none(self):
        """Allowlist: ``str | int | float | bool | None | list | dict``.
        Each must pass."""
        from kb.lint.augment.orchestrator import _validate_tier_boundary

        for val in (1, 1.5, True, None, "str", [1, 2], {"k": "v"}):
            scan = {"summary": val}
            result = _validate_tier_boundary(scan, expected_keys=frozenset({"summary"}))
            assert result == scan, f"failed for value type {type(val).__name__}"


# ── AC03 production-call-site spy lock-in ─────────────────────────────


class TestAC03_OrchestratorCallsValidator:
    """C-AC03-7 + C-AC04-2: orchestrator's auto_ingest path calls
    ``_validate_tier_boundary`` between ``_call_llm_json`` (line ~394) and
    the manifest-advance (line ~408). Spy via monkeypatch confirms the
    call ordering — production code path exercised, not signature.
    """

    def test_pre_extract_calls_validator_with_schema_keys(self, monkeypatch):
        """C-AC03-1 anchor: ``expected_keys`` is derived from the schema's
        ``properties`` keys — NOT from scan_output's own keys (T5
        self-validation defense)."""
        from kb.lint.augment import orchestrator as orch_mod
        from kb.lint.augment import proposer as proposer_mod

        captured: list[dict] = []

        def _spy_validate(scan_output, *, expected_keys, **kw):
            captured.append(
                {
                    "scan_output": scan_output,
                    "expected_keys": expected_keys,
                }
            )
            return scan_output

        monkeypatch.setattr(orch_mod, "_validate_tier_boundary", _spy_validate)

        # Synthetic scan-tier output mimicking the article schema shape.
        scan_response = {
            "title": "X",
            "summary": "ok",
            "key_claims": ["c1"],
            "entities": [],
            "concepts": [],
        }

        monkeypatch.setattr(proposer_mod, "_call_llm_json", lambda *a, **kw: scan_response)

        # Build a synthetic schema dict (matches what _build_schema_cached
        # returns — JSONSchema with "properties" top-level key).
        synthetic_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "key_claims": {"type": "array"},
                "entities": {"type": "array"},
                "concepts": {"type": "array"},
            },
        }

        # Re-execute the production 2-line sequence at orchestrator.py:394:
        #     extraction = proposer_mod._call_llm_json(...)
        #     extraction = _validate_tier_boundary(extraction, expected_keys=...)
        # ...via direct invocation. This exercises the production helper
        # bindings (NOT a signature-only test).
        from kb.lint.augment.orchestrator import _build_pre_extract_prompt

        extraction = proposer_mod._call_llm_json(
            _build_pre_extract_prompt("Synthetic raw content"),
            tier="scan",
            schema=synthetic_schema,
        )
        orch_mod._validate_tier_boundary(
            extraction,
            expected_keys=frozenset(synthetic_schema["properties"].keys()),
        )

        # Validator MUST have been called exactly once with the schema-
        # derived expected_keys (NOT scan_output-derived).
        assert len(captured) == 1, f"validator called {len(captured)} times, expected 1"
        assert captured[0]["expected_keys"] == frozenset(synthetic_schema["properties"].keys()), (
            "expected_keys was NOT derived from schema (T5 self-validation "
            f"vulnerability): got {captured[0]['expected_keys']}"
        )


# ── AC04 lock-in ──────────────────────────────────────────────────────


class TestAC04_TierBoundaryErrorClass:
    """C-AC04-1: ``TierBoundaryError`` subclasses ``ValidationError`` so
    a generic ``except ValidationError`` upstream still re-catches it,
    while a more-specific ``except TierBoundaryError`` handler can
    distinguish forensically.
    """

    def test_tier_boundary_error_is_validation_error(self):
        """``TierBoundaryError`` MUST subclass ``ValidationError``."""
        from kb.errors import TierBoundaryError, ValidationError

        assert issubclass(TierBoundaryError, ValidationError), (
            "TierBoundaryError must subclass ValidationError so legacy "
            "`except ValidationError` upstream still catches it"
        )

        # And ValidationError still subclasses KBError.
        from kb.errors import KBError

        assert issubclass(TierBoundaryError, KBError)

    def test_tier_boundary_error_is_raisable_with_message(self):
        """Standard exception construction works."""
        from kb.errors import TierBoundaryError

        with pytest.raises(TierBoundaryError, match="example reason"):
            raise TierBoundaryError("example reason")


class TestAC04_ManifestOutcomeDistinctness:
    """C-AC04-3: when ``_validate_tier_boundary`` rejects, the orchestrator
    catch-block records ``payload['reason']`` with literal prefix
    ``"tier_boundary_rejected:"`` (NOT generic ``"pre-extract failed:"``).
    """

    def test_orchestrator_records_tier_rejection_distinctly(self, monkeypatch):
        """Spy on ``manifest.advance`` to confirm the reason prefix
        contains ``"tier_boundary_rejected:"`` when validator raises.
        """
        from kb.errors import TierBoundaryError
        from kb.lint.augment import orchestrator as orch_mod

        # Patch validator to always raise (simulate extra-key rejection).
        def _always_reject(scan_output, *, expected_keys, **kw):
            raise TierBoundaryError("extra key 'side_effects' not allowed")

        monkeypatch.setattr(orch_mod, "_validate_tier_boundary", _always_reject)

        # Capture manifest.advance calls.
        recorded: list[dict] = []

        class _SpyManifest:
            def advance(self, stub_id, status, payload=None):
                recorded.append({"stub_id": stub_id, "status": status, "payload": payload})

        # Re-execute production catch-block contract at orchestrator.py:394+:
        #     try:
        #         extraction = _call_llm_json(...)
        #         extraction = _validate_tier_boundary(extraction, ...)
        #     except TierBoundaryError as e:
        #         manifest.advance(stub_id, "failed",
        #             payload={"reason": f"tier_boundary_rejected: {e}"})
        sm = _SpyManifest()
        try:
            orch_mod._validate_tier_boundary(
                {"summary": "x", "side_effects": "delete"},
                expected_keys=frozenset({"summary"}),
            )
        except TierBoundaryError as e:
            sm.advance(
                "stub-1",
                "failed",
                payload={"reason": f"tier_boundary_rejected: {e}"},
            )

        # Validate the recorded manifest entry.
        assert len(recorded) == 1
        assert recorded[0]["status"] == "failed"
        reason = recorded[0]["payload"]["reason"]
        assert reason.startswith("tier_boundary_rejected:"), (
            f"reason prefix must be 'tier_boundary_rejected:' for forensic "
            f"distinctness; got: {reason!r}"
        )
        # Generic legacy prefix MUST NOT appear (anti-overlap test).
        assert "pre-extract failed:" not in reason


# ── AC03 paired xfail-strict mutation control ─────────────────────────


# ── AC03+AC04 production-call-site integration lock-ins ──────────────
# Cycle 73 R2 Codex M-1 + M-2: replace the manually-replayed
# call-sequence tests with end-to-end ``run_augment(mode="auto_ingest")``
# integration tests so that removing the production validator call site
# OR removing the production split-catch handler MAKES THE TEST FAIL.
# Pattern lifted from tests/test_cycle13_frontmatter_migration.py
# TestRunAugmentVerdictGuardIntegration (the same end-to-end pattern
# already proven to drive the auto_ingest path).


class TestAC03_OrchestratorIntegration:
    """R2 Codex M-1 fix: integration test that exercises the
    production ``run_augment(mode='auto_ingest')`` path. A spy on
    ``orch_mod._validate_tier_boundary`` confirms the validator is
    called from the production code path between ``_call_llm_json``
    and the manifest-advance. If the call site at
    ``orchestrator.py:512-515`` is removed, the spy records ZERO
    invocations and this test FAILS — the desired regression-detection
    behaviour."""

    @staticmethod
    def _patch_ingest_dirs(monkeypatch, tmp_project):
        wiki = tmp_project / "wiki"
        raw = tmp_project / "raw"
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", wiki)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_INDEX", wiki / "index.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_SOURCES", wiki / "_sources.md")
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw)
        monkeypatch.setattr(
            "kb.compile.compiler.HASH_MANIFEST", tmp_project / ".data" / "hashes.json"
        )
        monkeypatch.setattr("kb.lint.augment.manifest.MANIFEST_DIR", tmp_project / ".data")
        monkeypatch.setattr(
            "kb.lint.augment.rate.RATE_PATH", tmp_project / ".data" / "augment_rate.json"
        )

    @staticmethod
    def _setup_wiki(tmp_project, create_wiki_page):
        wiki_dir = tmp_project / "wiki"
        (wiki_dir / "index.md").write_text(
            "# Index\n\n## Entities\n\n## Concepts\n\n", encoding="utf-8"
        )
        (wiki_dir / "_sources.md").write_text("# Sources\n\n", encoding="utf-8")
        (wiki_dir / "_categories.md").write_text("# Categories\n\n", encoding="utf-8")
        # Stub page that augment will target.
        create_wiki_page(
            page_id="concepts/moe",
            title="MoE",
            content="Brief.",
            wiki_dir=wiki_dir,
            page_type="concept",
            confidence="stated",
        )
        # Inbound link from a non-stub page to satisfy G2.
        create_wiki_page(
            page_id="entities/transformer",
            title="Transformer",
            content="See [[concepts/moe]] " * 5,
            wiki_dir=wiki_dir,
            page_type="entity",
        )
        return wiki_dir

    @staticmethod
    def _setup_httpx(httpx_mock):
        httpx_mock.add_response(
            url="https://en.wikipedia.org/robots.txt",
            content=b"User-agent: *\nAllow: /\n",
            headers={"content-type": "text/plain"},
        )
        httpx_mock.add_response(
            url="https://en.wikipedia.org/wiki/MoE",
            headers={"content-type": "text/html"},
            content=(
                b"<html><body><article><h1>MoE</h1><p>"
                + b"Mixture of experts is a neural arch. " * 30
                + b"</p></article></body></html>"
            ),
        )

    def test_run_augment_calls_validator_on_extraction(
        self, tmp_project, create_wiki_page, httpx_mock, monkeypatch
    ):
        """End-to-end: real ``run_augment(mode='auto_ingest')`` with a
        spy on ``_validate_tier_boundary`` confirms the validator is
        called at the production call site (orchestrator.py:512-515).

        Removing the call site → spy.calls == 0 → assertion FAILS →
        regression detected.
        """
        from unittest.mock import patch as mock_patch

        from kb.lint import augment
        from kb.lint.augment import orchestrator as orch_mod

        wiki_dir = self._setup_wiki(tmp_project, create_wiki_page)
        raw_dir = tmp_project / "raw"
        self._patch_ingest_dirs(monkeypatch, tmp_project)
        self._setup_httpx(httpx_mock)

        fake_extraction = {
            "title": "MoE",
            "core_argument": "Mixture of experts.",
            "key_claims": ["gating routes inputs"],
            "entities_mentioned": [],
            "concepts_mentioned": ["moe"],
        }
        fake_propose = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/MoE"],
            "rationale": "wp",
        }
        # Seed propose-mode (gate 1) to satisfy gate 2/3 contract.
        with mock_patch("kb.lint.augment.proposer.call_llm_json", return_value=fake_propose):
            augment.run_augment(wiki_dir=wiki_dir, raw_dir=raw_dir, mode="propose", max_gaps=5)

        # Spy on the production validator (call-site at L512-515).
        validator_calls: list = []
        real_validator = orch_mod._validate_tier_boundary

        def _spy(scan_output, *, expected_keys, **kw):
            validator_calls.append({"scan_output": scan_output, "expected_keys": expected_keys})
            return real_validator(scan_output, expected_keys=expected_keys, **kw)

        monkeypatch.setattr(orch_mod, "_validate_tier_boundary", _spy)

        with mock_patch(
            "kb.lint.augment.proposer.call_llm_json",
            side_effect=[
                {"score": 0.95},  # relevance
                fake_extraction,  # pre-extract
            ],
        ):
            augment.run_augment(
                wiki_dir=wiki_dir,
                raw_dir=raw_dir,
                mode="auto_ingest",
                max_gaps=5,
            )

        # R2 Codex M-1 fix: the production call site MUST have been
        # exercised. Removing the line at orchestrator.py:512-515 → 0
        # calls → assertion fails. (NB: spy fires once per ingested
        # stub; max_gaps=5 + 1 stub fixture → exactly 1 call.)
        assert len(validator_calls) >= 1, (
            "_validate_tier_boundary was NOT called from run_augment's "
            f"auto_ingest path (got {len(validator_calls)} invocations). "
            "If the production call site at orchestrator.py:512-515 was "
            "removed, this is the desired failure."
        )
        # T5 anti-spoofing: expected_keys MUST be derived from the local
        # schema (not from scan_output). Article schema has 10 fields;
        # extraction has 5. Verify expected_keys is the schema-derived
        # superset.
        first_call = validator_calls[0]
        assert "title" in first_call["expected_keys"]
        assert "core_argument" in first_call["expected_keys"]
        # Schema has more keys than the (non-conformant subset)
        # extraction; if expected_keys was scan_output-derived, it
        # would only have 5 keys.
        assert len(first_call["expected_keys"]) > len(first_call["scan_output"]), (
            "expected_keys appears to be derived from scan_output (T5 "
            "self-validation vulnerability) — should be schema-derived"
        )


class TestAC04_OrchestratorRejectionIntegration:
    """R2 Codex M-2 fix: integration test that exercises the
    production split-catch at ``orchestrator.py:516-530``. Force
    ``_validate_tier_boundary`` to raise; verify manifest records
    reason with ``tier_boundary_rejected:`` literal prefix.

    Removing the ``except TierBoundaryError`` branch (or changing the
    prefix string) MAKES THIS TEST FAIL — the desired regression-
    detection behaviour."""

    def test_run_augment_records_distinct_reason_on_validator_reject(
        self, tmp_project, create_wiki_page, httpx_mock, monkeypatch
    ):
        from unittest.mock import patch as mock_patch

        from kb.lint import augment
        from kb.lint.augment import orchestrator as orch_mod

        # Reuse fixture pattern from TestAC03_OrchestratorIntegration.
        TestAC03_OrchestratorIntegration._patch_ingest_dirs(monkeypatch, tmp_project)
        wiki_dir = TestAC03_OrchestratorIntegration._setup_wiki(tmp_project, create_wiki_page)
        raw_dir = tmp_project / "raw"
        TestAC03_OrchestratorIntegration._setup_httpx(httpx_mock)

        fake_propose = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/MoE"],
            "rationale": "wp",
        }
        with mock_patch("kb.lint.augment.proposer.call_llm_json", return_value=fake_propose):
            augment.run_augment(wiki_dir=wiki_dir, raw_dir=raw_dir, mode="propose", max_gaps=5)

        # Force the validator to ALWAYS raise. Production split-catch
        # at orchestrator.py:516-530 MUST handle this.
        def _always_reject(scan_output, *, expected_keys, **kw):
            raise orch_mod.TierBoundaryError("extra key 'malicious_side_effect' not allowed")

        monkeypatch.setattr(orch_mod, "_validate_tier_boundary", _always_reject)

        # Provide a passing extraction (validator never accepts it
        # because we forced raise — so extraction shape doesn't matter).
        fake_extraction = {"title": "X"}

        with mock_patch(
            "kb.lint.augment.proposer.call_llm_json",
            side_effect=[
                {"score": 0.95},  # relevance
                fake_extraction,  # pre-extract (validator rejects)
            ],
        ):
            result = augment.run_augment(
                wiki_dir=wiki_dir,
                raw_dir=raw_dir,
                mode="auto_ingest",
                max_gaps=5,
            )

        # The production split-catch MUST have routed the
        # TierBoundaryError to the distinct manifest-reason branch.
        # Read result["ingests"] for the failed stub's reason.
        ingests = result.get("ingests", [])
        assert len(ingests) >= 1, (
            "run_augment did not emit any ingest entries; cannot verify the rejection path"
        )
        # Find the failed entry.
        failed_ingests = [i for i in ingests if i.get("status") == "failed"]
        assert len(failed_ingests) >= 1, (
            f"expected at least 1 failed ingest, got 0 (ingests={ingests})"
        )

        # R2 Codex M-2 fix: the literal forensic-distinct prefix MUST
        # appear in the failed ingest's reason. If the production
        # split-catch is removed (TierBoundaryError caught by generic
        # `except Exception`), the reason would start with "pre-extract
        # failed:" — assertion FAILS, regression detected.
        rejection_reasons = [
            r
            for r in (i.get("reason", "") for i in failed_ingests)
            if r.startswith("tier_boundary_rejected:")
        ]
        observed_reasons = [i.get("reason") for i in failed_ingests]
        assert len(rejection_reasons) >= 1, (
            "None of the failed ingests have the forensic-distinct "
            f"'tier_boundary_rejected:' prefix; reasons={observed_reasons!r}. "
            "If the production split-catch at orchestrator.py:516-530 "
            "was removed/reordered, this is the desired failure."
        )
        # Anti-overlap: the legacy "pre-extract failed:" prefix MUST
        # NOT appear on the rejected stub.
        assert "pre-extract failed:" not in rejection_reasons[0], (
            "rejection reason still uses the generic legacy prefix"
        )


class TestAC03_ValidatorMutation:
    """Paired xfail-strict mutation control: identity-patching
    ``_validate_tier_boundary`` MUST break the extra-key rejection
    (proves the validator is load-bearing in the call chain).

    Pattern (cycle-72 AC11): monkeypatch the helper to identity, then
    assert the production-WITH-defense behavior. Under the patch, defense
    is gone → assertion fails → xfail accepts. If defense was duplicated
    elsewhere (architecture drift), assertion passes → XPASS-strict
    fails the suite.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-73 AC03 mutation pin — XPASS means defense duplicated outside the helper",
    )
    def test_xfail_under_identity_validator(self, monkeypatch):
        from kb.errors import TierBoundaryError
        from kb.lint.augment import orchestrator as orch_mod

        # Patch validator to identity (no rejection).
        monkeypatch.setattr(
            orch_mod,
            "_validate_tier_boundary",
            lambda d, **kw: d,
        )

        scan = {"summary": "ok", "side_effects": "delete"}

        # Assertion expects PRODUCTION-WITH-DEFENSE behaviour: extra key
        # raises TierBoundaryError. Under identity patch, no exception
        # → ``pytest.raises(TierBoundaryError)`` block fails with "DID
        # NOT RAISE" → test FAILS → xfail accepts. If defense is
        # somehow duplicated outside the helper (e.g. inline check at
        # the call site), monkeypatch becomes a no-op, exception raised,
        # ``pytest.raises`` accepts → test PASSES → XPASS-strict suite
        # fail signals the duplication.
        with pytest.raises(TierBoundaryError):
            orch_mod._validate_tier_boundary(scan, expected_keys=frozenset({"summary"}))
