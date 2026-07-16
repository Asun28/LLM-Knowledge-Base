"""Cycle 74 AC01-AC03 — Tier-boundary verifier hardening.

Closes the 3 cycle-74+ deferred entries filed in BACKLOG Phase 4.5 LOW
after cycle 73:

- AC01 (cycle-73 R2 DeepSeek F-2): ``max_keys: int = 500`` DoS bound on
  ``_validate_tier_boundary`` — caps the key count of the root dict AND
  every nested dict so a broad-schema scan-tier response cannot exhaust
  memory in the depth walker.
- AC02 (cycle-73 R1 Opus C2): same-class peer expansion — the two
  ``_call_llm_json(tier="scan", schema=...)`` call sites in
  ``proposer.py`` (``_propose_urls``, ``_relevance_score``) now re-gate
  their responses through ``_validate_tier_boundary`` with site-specific
  ``expected_keys`` / ``required_keys`` derived from the LOCAL schema
  constants (T5 anti-spoofing). Rejection is fail-closed (abstain / 0.0)
  with the forensic-distinct ``tier_boundary_rejected:`` marker.
  Mechanically, the validator moved from ``orchestrator.py`` into the
  new leaf module ``kb.lint.augment.tier_boundary`` (orchestrator
  imports proposer at module level, so proposer could not import back);
  ``orchestrator.py`` re-exports both names so the cycle-73 monkeypatch
  surface is unchanged.
- AC03 (cycle-73 R2 F-3): optional ``required_keys`` enforcement —
  derived from the JSONSchema ``"required"`` list, separately from
  ``expected_keys``. The ``frozenset()`` default preserves the cycle-73
  contract that optional-field subsets are accepted.

Per ``feedback_test_behavior_over_signature``: the AC02 call-site tests
invoke the production functions directly — the validator call lives
INSIDE ``_propose_urls`` / ``_relevance_score``, so a direct call IS the
production path (unlike cycle-73's orchestrator-body call site, which
needed the run_augment integration test).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ── AC01 — max_keys DoS bound ─────────────────────────────────────────


class TestAC01_MaxKeysBound:
    """C-AC01: root and nested dicts with more than ``max_keys`` keys are
    rejected; exactly ``max_keys`` keys pass; the bound is overridable.

    Cycle-20 L1 reload-leak guard: ``TierBoundaryError`` is late-bound
    via the already-imported module attribute (see the cycle-73 test
    file's class docstring for the full rationale).
    """

    def test_rejects_root_dict_over_max_keys(self):
        """501-key root dict → TierBoundaryError even when every key is
        in ``expected_keys`` (the size check fires BEFORE the extra-key
        set difference — cheap-first)."""
        from kb.lint.augment import tier_boundary as tb_mod

        keys = [f"k{i}" for i in range(501)]
        scan_output = dict.fromkeys(keys, "v")
        with pytest.raises(tb_mod.TierBoundaryError, match="max_keys"):
            tb_mod._validate_tier_boundary(
                scan_output, expected_keys=frozenset(keys)
            )

    def test_rejects_nested_dict_over_max_keys(self):
        """Nested 501-key dict → TierBoundaryError. The extra-key check
        only covers the ROOT dict, so nested dicts are the realistic
        mass-key DoS surface (broad-schema scenario from the BACKLOG
        entry)."""
        from kb.lint.augment import tier_boundary as tb_mod

        scan_output = {"summary": {f"k{i}": 1 for i in range(501)}}
        with pytest.raises(tb_mod.TierBoundaryError, match="max_keys"):
            tb_mod._validate_tier_boundary(
                scan_output, expected_keys=frozenset({"summary"})
            )

    def test_accepts_exactly_max_keys(self):
        """Boundary: exactly 500 keys (root and nested) passes."""
        from kb.lint.augment.tier_boundary import _validate_tier_boundary

        keys = [f"k{i}" for i in range(500)]
        scan_output = dict.fromkeys(keys, "v")
        result = _validate_tier_boundary(scan_output, expected_keys=frozenset(keys))
        assert result is scan_output

        nested = {"summary": {f"k{i}": 1 for i in range(500)}}
        result = _validate_tier_boundary(nested, expected_keys=frozenset({"summary"}))
        assert result is nested

    def test_max_keys_override(self):
        """The override path from the BACKLOG entry: ``max_keys=2``
        rejects a 3-key nested dict that the default would accept."""
        from kb.lint.augment import tier_boundary as tb_mod

        scan_output = {"summary": {"a": 1, "b": 2, "c": 3}}
        expected = frozenset({"summary"})

        # Default (500): passes.
        assert tb_mod._validate_tier_boundary(scan_output, expected_keys=expected)

        # Tightened override: rejects.
        with pytest.raises(tb_mod.TierBoundaryError, match="max_keys=2"):
            tb_mod._validate_tier_boundary(
                scan_output, expected_keys=expected, max_keys=2
            )


# ── AC03 — required_keys enforcement ──────────────────────────────────


class TestAC03_RequiredKeysEnforcement:
    """C-AC03: keys listed in ``required_keys`` must be present; the
    empty default preserves the cycle-73 optional-subset contract."""

    def test_rejects_missing_required_key(self):
        from kb.lint.augment import tier_boundary as tb_mod

        scan_output = {"urls": ["https://example.org"]}
        with pytest.raises(tb_mod.TierBoundaryError, match="required key"):
            tb_mod._validate_tier_boundary(
                scan_output,
                expected_keys=frozenset({"action", "urls"}),
                required_keys=frozenset({"action"}),
            )

    def test_accepts_present_required_key(self):
        from kb.lint.augment.tier_boundary import _validate_tier_boundary

        scan_output = {"action": "abstain"}
        result = _validate_tier_boundary(
            scan_output,
            expected_keys=frozenset({"action", "urls", "reason"}),
            required_keys=frozenset({"action"}),
        )
        assert result is scan_output

    def test_default_preserves_cycle73_subset_contract(self):
        """No ``required_keys`` argument → missing keys are still NOT a
        rejection cause (back-compat with every cycle-73 caller)."""
        from kb.lint.augment.tier_boundary import _validate_tier_boundary

        scan_output = {"summary": "ok"}
        result = _validate_tier_boundary(
            scan_output,
            expected_keys=frozenset({"summary", "title", "evidence"}),
        )
        assert result is scan_output


# ── AC02 — module extraction + re-export back-compat ─────────────────


class TestAC02_ReExportBackCompat:
    """The orchestrator re-export IS the same object as the leaf-module
    definition — guards against drift where orchestrator re-grows its
    own copy (which would silently decouple the two patch surfaces)."""

    def test_orchestrator_reexports_leaf_module_symbols(self):
        from kb.lint.augment import orchestrator as orch_mod
        from kb.lint.augment import tier_boundary as tb_mod

        assert orch_mod._validate_tier_boundary is tb_mod._validate_tier_boundary
        assert orch_mod._TBV_ALLOWED_VALUE_TYPES is tb_mod._TBV_ALLOWED_VALUE_TYPES

    def test_proposer_binds_leaf_module_symbol(self):
        from kb.lint.augment import proposer as proposer_mod
        from kb.lint.augment import tier_boundary as tb_mod

        assert proposer_mod._validate_tier_boundary is tb_mod._validate_tier_boundary


# ── AC02 — _propose_urls call-site re-gate ────────────────────────────


_STUB = {
    "page_id": "concepts/x",
    "title": "X",
    "page_type": "concept",
    "frontmatter": {},
    "body": "",
}


class TestAC02_ProposeUrlsRegate:
    """The scan-tier proposer response is validated before consumption;
    rejection abstains with the forensic-distinct reason prefix."""

    def test_extra_key_response_abstains_with_distinct_reason(self):
        """LLM-injected extra key → fail-closed abstain, reason prefixed
        ``tier_boundary_rejected:`` (NOT the generic ``proposer LLM
        error:`` prefix — anti-overlap for forensic grep)."""
        from kb.lint.augment import _propose_urls

        fake_response = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/X"],
            "rationale": "wp",
            "side_effects": "delete_all",
        }
        with patch("kb.lint.augment.proposer.call_llm_json", return_value=fake_response):
            result = _propose_urls(stub=dict(_STUB), purpose_text="")

        assert result["action"] == "abstain"
        assert result["reason"].startswith("tier_boundary_rejected:")
        assert "proposer LLM error" not in result["reason"]

    def test_missing_required_action_abstains_with_distinct_reason(self):
        """AC03 at this site: ``_PROPOSER_SCHEMA['required'] == ['action']``
        → a response without ``action`` is a tier-boundary rejection
        (previously fell through to the ``unexpected action`` branch)."""
        from kb.lint.augment import _propose_urls

        with patch(
            "kb.lint.augment.proposer.call_llm_json",
            return_value={"urls": ["https://en.wikipedia.org/wiki/X"]},
        ):
            result = _propose_urls(stub=dict(_STUB), purpose_text="")

        assert result["action"] == "abstain"
        assert result["reason"].startswith("tier_boundary_rejected:")

    def test_well_formed_response_still_proposes(self):
        """Positive control: schema-conformant response passes the
        re-gate unchanged (no false-positive abstains)."""
        from kb.lint.augment import _propose_urls

        fake_response = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/Mixture_of_experts"],
            "rationale": "wp",
        }
        with patch("kb.lint.augment.proposer.call_llm_json", return_value=fake_response):
            result = _propose_urls(stub=dict(_STUB), purpose_text="")

        assert result["action"] == "propose"
        assert result["urls"] == ["https://en.wikipedia.org/wiki/Mixture_of_experts"]

    def test_validator_called_with_schema_derived_keysets(self, monkeypatch):
        """T5 anti-spoofing anchor: ``expected_keys`` / ``required_keys``
        are derived from the LOCAL ``_PROPOSER_SCHEMA`` constant — not
        from the response."""
        from kb.lint.augment import proposer as proposer_mod

        captured: list[dict] = []

        def _spy(scan_output, *, expected_keys, required_keys=frozenset(), **kw):
            captured.append(
                {"expected_keys": expected_keys, "required_keys": required_keys}
            )
            return scan_output

        monkeypatch.setattr(proposer_mod, "_validate_tier_boundary", _spy)

        # Response deliberately NON-conformant to the schema keysets: if
        # the call site derived keys from the response, the assert below
        # would see {"action"} only.
        with patch(
            "kb.lint.augment.proposer.call_llm_json",
            return_value={"action": "abstain"},
        ):
            proposer_mod._propose_urls(stub=dict(_STUB), purpose_text="")

        assert len(captured) == 1
        assert captured[0]["expected_keys"] == frozenset(
            proposer_mod._PROPOSER_SCHEMA["properties"].keys()
        )
        assert captured[0]["required_keys"] == frozenset(
            proposer_mod._PROPOSER_SCHEMA["required"]
        )


# ── AC02 — _relevance_score call-site re-gate ─────────────────────────


class TestAC02_RelevanceScoreRegate:
    """The scan-tier relevance response is validated before consumption;
    rejection fails closed to 0.0 (below any sane threshold)."""

    def test_extra_key_response_returns_zero(self):
        from kb.lint.augment import _relevance_score

        with patch(
            "kb.lint.augment.proposer.call_llm_json",
            return_value={"score": 0.9, "side_effects": "delete_all"},
        ):
            score = _relevance_score(stub_title="X", extracted_text="some text")
        assert score == 0.0

    def test_non_dict_response_returns_zero_without_crash(self):
        """Latent-crash closure: a non-dict response previously reached
        ``response.get(...)`` OUTSIDE the try block → AttributeError
        propagated to the caller. The re-gate now converts it to a
        fail-closed 0.0."""
        from kb.lint.augment import _relevance_score

        with patch(
            "kb.lint.augment.proposer.call_llm_json",
            return_value=[0.9],  # list, not dict
        ):
            score = _relevance_score(stub_title="X", extracted_text="some text")
        assert score == 0.0

    def test_missing_required_score_returns_zero(self):
        """AC03 at this site: ``_RELEVANCE_SCHEMA['required'] == ['score']``
        → empty dict is a tier-boundary rejection → 0.0."""
        from kb.lint.augment import _relevance_score

        with patch("kb.lint.augment.proposer.call_llm_json", return_value={}):
            score = _relevance_score(stub_title="X", extracted_text="some text")
        assert score == 0.0

    def test_well_formed_response_still_scores(self):
        """Positive control: conformant response returns its score."""
        from kb.lint.augment import _relevance_score

        with patch(
            "kb.lint.augment.proposer.call_llm_json", return_value={"score": 0.85}
        ):
            score = _relevance_score(stub_title="X", extracted_text="some text")
        assert score == 0.85

    def test_validator_called_with_schema_derived_keysets(self, monkeypatch):
        """T5 anti-spoofing anchor for the relevance site."""
        from kb.lint.augment import proposer as proposer_mod

        captured: list[dict] = []

        def _spy(scan_output, *, expected_keys, required_keys=frozenset(), **kw):
            captured.append(
                {"expected_keys": expected_keys, "required_keys": required_keys}
            )
            return scan_output

        monkeypatch.setattr(proposer_mod, "_validate_tier_boundary", _spy)

        with patch(
            "kb.lint.augment.proposer.call_llm_json", return_value={"score": 0.5}
        ):
            proposer_mod._relevance_score(stub_title="X", extracted_text="some text")

        assert len(captured) == 1
        assert captured[0]["expected_keys"] == frozenset(
            proposer_mod._RELEVANCE_SCHEMA["properties"].keys()
        )
        assert captured[0]["required_keys"] == frozenset(
            proposer_mod._RELEVANCE_SCHEMA["required"]
        )


# ── AC03 — orchestrator call-site required_keys plumb ─────────────────


class TestAC03_OrchestratorRequiredKeysPlumb:
    """The auto_ingest call site (orchestrator.py L512 region) now passes
    ``required_keys=frozenset(schema.get('required', []))`` alongside the
    cycle-73 ``expected_keys``. Spy replay of the production 2-line
    sequence with the PRODUCTION article schema (via
    ``_build_schema_cached``) — the schema-derivation expressions are
    asserted verbatim against the captured kwargs."""

    def test_required_keys_derived_from_article_schema(self, monkeypatch):
        from kb.ingest.extractors import _build_schema_cached
        from kb.lint.augment import orchestrator as orch_mod
        from kb.lint.augment import proposer as proposer_mod

        captured: list[dict] = []

        def _spy(scan_output, *, expected_keys, required_keys=frozenset(), **kw):
            captured.append(
                {"expected_keys": expected_keys, "required_keys": required_keys}
            )
            return scan_output

        monkeypatch.setattr(orch_mod, "_validate_tier_boundary", _spy)

        schema = _build_schema_cached("article")
        scan_response = {"title": "X"}
        monkeypatch.setattr(
            proposer_mod, "_call_llm_json", lambda *a, **kw: scan_response
        )

        # Replay the production sequence at the orchestrator call site.
        extraction = proposer_mod._call_llm_json(
            orch_mod._build_pre_extract_prompt("Synthetic raw content"),
            tier="scan",
            schema=schema,
        )
        orch_mod._validate_tier_boundary(
            extraction,
            expected_keys=frozenset(schema.get("properties", {}).keys()),
            required_keys=frozenset(schema.get("required", [])),
        )

        assert len(captured) == 1
        assert captured[0]["required_keys"] == frozenset(schema.get("required", []))
        # Fix 2.6 in build_extraction_schema guarantees a non-empty
        # required list whenever properties exist — so this plumb is
        # never vacuous for the article schema.
        assert captured[0]["required_keys"], (
            "article schema 'required' list is empty — the required_keys "
            "plumb would be vacuous; check build_extraction_schema Fix 2.6"
        )
        assert captured[0]["required_keys"] <= captured[0]["expected_keys"]


# ── Paired xfail-strict mutation controls (cycle-72 AC11 pattern) ─────


class TestAC02_ProposerValidatorMutation:
    """Identity-patching the proposer's imported validator binding MUST
    break the extra-key abstain (proves the re-gate is load-bearing at
    the ``_propose_urls`` call site)."""

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-74 AC02 mutation pin — XPASS means defense duplicated outside the validator",
    )
    def test_xfail_propose_urls_under_identity_validator(self, monkeypatch):
        from kb.lint.augment import proposer as proposer_mod

        monkeypatch.setattr(
            proposer_mod, "_validate_tier_boundary", lambda d, **kw: d
        )

        fake_response = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/X"],
            "rationale": "wp",
            "side_effects": "delete_all",
        }
        with patch("kb.lint.augment.proposer.call_llm_json", return_value=fake_response):
            result = proposer_mod._propose_urls(stub=dict(_STUB), purpose_text="")

        # Production-WITH-defense expectation: extra key → abstain.
        # Under the identity patch the propose path runs instead → this
        # assertion FAILS → xfail accepts. If it XPASSes, the rejection
        # logic was duplicated outside the validator (architecture drift).
        assert result["action"] == "abstain"

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-74 AC02 mutation pin — XPASS means defense duplicated outside the validator",
    )
    def test_xfail_relevance_score_under_identity_validator(self, monkeypatch):
        from kb.lint.augment import proposer as proposer_mod

        monkeypatch.setattr(
            proposer_mod, "_validate_tier_boundary", lambda d, **kw: d
        )

        with patch(
            "kb.lint.augment.proposer.call_llm_json",
            return_value={"score": 0.9, "side_effects": "delete_all"},
        ):
            score = proposer_mod._relevance_score(
                stub_title="X", extracted_text="some text"
            )

        # Production-WITH-defense expectation: extra key → 0.0. Under
        # the identity patch the score passes through (0.9) → FAILS →
        # xfail accepts.
        assert score == 0.0
