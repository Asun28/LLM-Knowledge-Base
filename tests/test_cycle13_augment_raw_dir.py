"""Cycle 13 — AC8/AC15: run_augment raw_dir derivation regression.

When caller supplies a custom ``wiki_dir`` but omits ``raw_dir``, the
orchestrator derives ``raw_dir = wiki_dir.parent / "raw"`` so augment runs
stay project-isolated. Mirrors the existing ``effective_data_dir``
derivation pattern.

The four sub-tests pin the four branches of the resolution decision:
1. wiki_dir override + raw_dir omitted → derived sibling
2. explicit raw_dir → honoured (custom path)
3. no kwargs → fallback to module-level RAW_DIR
4. explicit raw_dir == module RAW_DIR → honoured (proves ``raw_dir is not
   None`` branch, not value identity)

The branch logic is extracted to ``_resolve_raw_dir(wiki_dir, raw_dir)``
for direct testability — same pattern as cycle-13's
``_record_verdict_gap_callout`` extraction.
"""

from __future__ import annotations

from kb.lint import augment


class TestRawDirDerivation:
    """AC15 — four-branch derivation pin for _resolve_raw_dir."""

    def test_wiki_override_derives_raw_sibling(self, tmp_kb_env):
        """Branch 1: custom wiki_dir + raw_dir omitted → derive sibling."""
        wiki = tmp_kb_env / "wiki"
        resolved = augment._resolve_raw_dir(wiki, None)
        expected = wiki.parent / "raw"
        assert resolved == expected, f"expected derived raw_dir={expected}, got {resolved}"

    def test_explicit_raw_dir_honoured(self, tmp_kb_env):
        """Branch 2: explicit raw_dir → honoured even with wiki override."""
        wiki = tmp_kb_env / "wiki"
        custom_raw = tmp_kb_env / "custom-raw"
        resolved = augment._resolve_raw_dir(wiki, custom_raw)
        assert resolved == custom_raw, f"expected explicit custom_raw={custom_raw}, got {resolved}"

    def test_standard_run_uses_global_raw_dir(self, tmp_kb_env, monkeypatch):
        """Branch 3: default wiki_dir + no raw_dir → fallback to RAW_DIR."""
        patched_raw = tmp_kb_env / "raw-global"
        monkeypatch.setattr(augment, "RAW_DIR", patched_raw)
        # Use the module's WIKI_DIR (default) so the lexical comparison
        # ``wiki_dir != WIKI_DIR`` is False and the else-branch fires.
        resolved = augment._resolve_raw_dir(augment.WIKI_DIR, None)
        assert resolved == patched_raw, f"expected RAW_DIR={patched_raw}, got {resolved}"

    def test_explicit_raw_equals_global_honoured(self, tmp_kb_env, monkeypatch):
        """Branch 4: explicit raw_dir literally equals RAW_DIR → still honoured.

        Proves the branch is ``raw_dir is None`` (None-check), NOT a value
        identity check (``raw_dir == RAW_DIR``). A future refactor that
        accidentally changes the condition to value-comparison would derive
        a sibling instead of using the explicit pass.
        """
        wiki = tmp_kb_env / "wiki"
        patched_raw = tmp_kb_env / "raw-global"
        monkeypatch.setattr(augment, "RAW_DIR", patched_raw)
        resolved = augment._resolve_raw_dir(wiki, patched_raw)
        # MUST be the explicit value, NOT wiki.parent / "raw".
        assert resolved == patched_raw, (
            f"expected explicit RAW_DIR pass={patched_raw}, "
            f"got {resolved} (sibling-derivation regression?)"
        )

    def test_run_augment_invokes_resolver(self, tmp_kb_env, monkeypatch):
        """Integration sanity: run_augment routes raw_dir through _resolve_raw_dir.

        Patches the helper to a sentinel-returning spy and confirms run_augment
        produces the early-return summary expected when no proposals file
        exists, proving the helper IS reached on a real call.
        """
        wiki = tmp_kb_env / "wiki"
        sentinel = tmp_kb_env / "spy-raw"
        sentinel.mkdir()

        calls: list[tuple] = []
        real = augment._resolve_raw_dir

        def _spy(wd, rd):
            calls.append((wd, rd))
            return real(wd, rd) if rd is not None else sentinel

        monkeypatch.setattr(augment, "_resolve_raw_dir", _spy)
        # mode="execute" + no proposals.md => early return; spy must fire first.
        augment.run_augment(wiki_dir=wiki, mode="execute")

        assert calls, "spy never called — run_augment did not route through _resolve_raw_dir"
        assert calls[0][0] == wiki, f"unexpected wiki_dir arg: {calls[0]}"
        assert calls[0][1] is None, f"unexpected raw_dir arg: {calls[0]}"
