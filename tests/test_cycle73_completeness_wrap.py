"""Cycle 73 AC01 — ``build_completeness_context`` cap + ``wrap_wiki_context`` fence.

Tests for cycle-73 AC01: extends the cycle-71 AC03 + cycle-72 AC01 wrap-fence
defense to ``src/kb/lint/semantic.py:466 build_completeness_context`` —
the same-class peer of ``build_fidelity_context`` deferred per cycle-72
threat-model §T1 OOS scoping.

Per design-decision §1 + §11 (FROZEN at Step 5):
- Condition C-AC01-1: cap ``paired['page_content']`` at
  ``QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD`` BEFORE assembly via the
  shared ``_cap_page_content`` helper (cycle-72 R2 Codex M-1 marker
  reservation inherits automatically).
- Condition C-AC01-2: split assembled lines into header (outside fence) +
  body (inside fence) + closing (outside fence) — same shape as
  ``build_fidelity_context`` per cycle-71 AC03.
- Condition C-AC01-3: wrap body in ``wrap_wiki_context`` exactly once.

Threat-model: T1 (Tampering — closer-injection mid-page) + T2
(InformationDisclosure — oversized page bypasses cap → unbounded prompt).

Per ``feedback_test_behavior_over_signature``: behavioural assertions only.
Per cycle-22 L5: every CONDITIONS bullet from the design gate becomes a
test sub-AC.
"""

from __future__ import annotations

import pytest

from kb.config import QUERY_CONTEXT_MAX_CHARS


def _make_attacker_payload(prefix: str = "A" * 50, suffix: str = "B" * 50) -> str:
    """String with literal ``</wiki_context>`` planted mid-body.

    Used to assert the ``wrap_wiki_context`` closer-escape ran (T1 defense).
    """
    return f"{prefix}</wiki_context>{suffix}"


# ── AC01 lock-in ──────────────────────────────────────────────────────


class TestAC01_CompletenessPageContentCap:
    """AC01 lock-in: ``build_completeness_context`` caps
    ``paired['page_content']`` at ``QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD``
    via the shared ``_cap_page_content`` helper.

    Conditions covered:
    - C-AC01-1: cap at L466 site (build_completeness_context).
    - C-AC01-2: header / body / closing triplet shape.
    - C-AC01-3: single ``wrap_wiki_context`` fence around body only.
    """

    def _stub_paired_oversized(self) -> dict:
        from kb.utils.text import _FENCE_OVERHEAD

        oversized_body = "X" * (QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD + 1000)
        return {
            "page_content": oversized_body,
            "source_contents": [
                {"path": "raw/clean.md", "content": "small source content"}
            ],
        }

    def _stub_paired_under_cap(self) -> dict:
        return {
            "page_content": "small body",
            "source_contents": [
                {"path": "raw/clean.md", "content": "small source content"}
            ],
        }

    def _stub_paired_with_attacker(self) -> dict:
        return {
            "page_content": _make_attacker_payload("p-", "-p"),
            "source_contents": [
                {
                    "path": "raw/src.md",
                    "content": _make_attacker_payload("s-", "-s"),
                }
            ],
        }

    def test_completeness_context_includes_single_fence(self, monkeypatch):
        """C-AC01-3: assembled output contains EXACTLY ONE ``<wiki_context>``
        open and one close — single fence around body only."""
        from kb.lint import semantic as semantic_mod

        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: self._stub_paired_under_cap(),
        )
        out = semantic_mod.build_completeness_context("entities/test")

        assert out.count("<wiki_context>") == 1, (
            f"expected exactly 1 <wiki_context> open, got {out.count('<wiki_context>')}"
        )
        assert out.count("</wiki_context>") == 1, (
            f"expected exactly 1 </wiki_context> close, got "
            f"{out.count('</wiki_context>')}"
        )

    def test_completeness_oversized_page_truncated_with_marker(self, monkeypatch):
        """C-AC01-1 + C-AC01-2: oversized page is capped via
        ``_cap_page_content`` (marker present) AND the marker is at the
        end of the body region (cycle-24 L1 + cycle-72 R2 Codex M-2 strict
        endswith on bounded slice)."""
        from kb.lint import semantic as semantic_mod

        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: self._stub_paired_oversized(),
        )
        out = semantic_mod.build_completeness_context("entities/test")

        marker = "[truncated for context budget]"
        assert marker in out, "truncation marker missing on oversized page"

        # Strict endswith on bounded slice: extract the slice between
        # "## Wiki Page" and the next "\n---\n" (page-region trailing
        # separator), assert it ends with the marker.
        page_heading_idx = out.find("## Wiki Page")
        assert page_heading_idx >= 0, "## Wiki Page heading missing"
        sources_separator_idx = out.find("\n---\n", page_heading_idx)
        assert sources_separator_idx > page_heading_idx, (
            "page-region trailing separator missing"
        )
        page_body = out[page_heading_idx:sources_separator_idx]
        assert page_body.rstrip().endswith(marker), (
            "marker is NOT the LAST chars of the capped page-body region "
            f"(cycle-24 L1 strict endswith): tail={page_body[-200:]!r}"
        )

    def test_completeness_under_cap_passes_through_unchanged(self, monkeypatch):
        """Pages under the cap MUST pass through with NO truncation marker."""
        from kb.lint import semantic as semantic_mod

        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: self._stub_paired_under_cap(),
        )
        out = semantic_mod.build_completeness_context("entities/test")

        assert "[truncated for context budget]" not in out, (
            "truncation marker MUST NOT appear when content is under cap"
        )
        assert "small body" in out, "under-cap body must pass through unchanged"

    def test_completeness_capped_length_within_budget(self):
        """Cycle-72 L8 + R2 Codex M-1: capped content + marker MUST be
        ≤ max_chars (cap helper reserves marker length). AC01 reuses the
        same ``_cap_page_content`` helper, so this invariant carries over.
        """
        from kb.lint.semantic import _CAP_TRUNCATION_MARKER, _cap_page_content

        oversized = "X" * 10000
        capped = _cap_page_content(oversized, max_chars=1000)
        assert len(capped) <= 1000, (
            f"cap-math overshoot: capped length {len(capped)} > max_chars=1000 "
            "(marker not reserved within cap — cycle-72 R2 Codex M-1 fix)"
        )
        assert capped.endswith(_CAP_TRUNCATION_MARKER), (
            "truncation marker missing from cap helper output"
        )

    def test_completeness_attacker_closer_escaped(self, monkeypatch):
        """T1 defense: when ``paired['page_content']`` contains a literal
        ``</wiki_context>`` closer, ``wrap_wiki_context`` rewrites it to
        ``</wiki-context>`` (hyphen, not underscore) so the attacker
        cannot break out of the fence."""
        from kb.lint import semantic as semantic_mod

        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: self._stub_paired_with_attacker(),
        )
        out = semantic_mod.build_completeness_context("entities/test")

        # The fence is added once by wrap_wiki_context. Any additional
        # ``</wiki_context>`` would mean the attacker payload escaped.
        assert out.count("</wiki_context>") == 1, (
            f"attacker closer NOT escaped: count of </wiki_context> = "
            f"{out.count('</wiki_context>')} (must be 1 — only the wrap's own)"
        )
        # The escaped variant should appear (hyphen instead of underscore).
        assert "</wiki-context>" in out, (
            "escaped closer </wiki-context> not present — "
            "wrap_wiki_context._escape_wiki_context_close did not run"
        )

    def test_completeness_render_sources_budget_reserved(self, monkeypatch):
        """C-AC01-2: ``_render_sources`` is called with
        ``budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD`` so the
        wrapped total stays within budget."""
        from kb.lint import semantic as semantic_mod
        from kb.utils.text import _FENCE_OVERHEAD

        captured_budget: list[int | None] = []

        original_render = semantic_mod._render_sources

        def _spy(sources, lines, *, budget=None):
            captured_budget.append(budget)
            return original_render(sources, lines, budget=budget)

        monkeypatch.setattr(semantic_mod, "_render_sources", _spy)
        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: self._stub_paired_under_cap(),
        )

        semantic_mod.build_completeness_context("entities/test")

        assert captured_budget, "_render_sources was not called from completeness"
        expected = QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD
        assert expected in captured_budget, (
            f"_render_sources call did NOT pass budget=QUERY_CONTEXT_MAX_CHARS"
            f" - _FENCE_OVERHEAD ({expected}); captured budgets={captured_budget}"
        )


# ── AC01 paired xfail-strict mutation controls ────────────────────────


class TestAC01_CompletenessCapMutation:
    """Paired xfail-strict mutation control for AC01: identity-patching
    ``_cap_page_content`` MUST break the lock-in (proves cap is load-bearing).
    """

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-73 AC01 mutation pin — passing means cap reverted in completeness",
    )
    def test_xfail_under_identity_cap(self, monkeypatch):
        from kb.lint import semantic as semantic_mod
        from kb.utils.text import _FENCE_OVERHEAD

        oversized = "X" * (QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD + 1000)
        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: {
                "page_content": oversized,
                "source_contents": [{"path": "raw/x.md", "content": "s"}],
            },
        )
        # Replace _cap_page_content with identity (no truncation).
        monkeypatch.setattr(
            semantic_mod, "_cap_page_content", lambda text, _max: text
        )

        out = semantic_mod.build_completeness_context("entities/test")
        # Without the cap, marker should be missing. xfail-strict expects
        # this assertion to FAIL (i.e., marker IS missing → assertion
        # raises → xfail accepts). If the cap is implemented elsewhere
        # somehow, marker is present → assertion passes → xfail-strict
        # fails the suite, signalling production-side revert.
        assert "[truncated for context budget]" in out


class TestAC01_CompletenessWrapMutation:
    """Paired xfail-strict mutation control: identity-patching
    ``wrap_wiki_context`` MUST break the fence-presence assertion.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="cycle-73 AC01 mutation pin — passing means wrap reverted in completeness",
    )
    def test_xfail_under_identity_wrap(self, monkeypatch):
        from kb.lint import semantic as semantic_mod

        monkeypatch.setattr(
            semantic_mod,
            "pair_page_with_sources",
            lambda *a, **kw: {
                "page_content": "small body",
                "source_contents": [{"path": "raw/x.md", "content": "s"}],
            },
        )
        # Replace wrap_wiki_context with identity (no fence).
        monkeypatch.setattr(
            semantic_mod, "wrap_wiki_context", lambda text: text
        )

        out = semantic_mod.build_completeness_context("entities/test")
        # Without the wrap, fence tag must be absent. xfail-strict expects
        # this to FAIL (i.e., tag IS absent).
        assert "<wiki_context>" in out
