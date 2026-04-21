"""Cycle 19 AC14-anchor — machine-enforced regression of cycle-17 AC1 prune-base fix.

AC14 was DROPPED from cycle-19 production scope at the design gate because
the fix was already shipped in cycle-17 AC1 (compiler.py:270 + compiler.py:452
both consistently use `_canonical_rel_path` / `raw_dir.resolve().parent`).
Per cycle-15 L2 (DROP-with-test-anchor-retention), this test stays as a
regression anchor so a future refactor cannot silently re-introduce the
divergence class.

This test deliberately uses `inspect.getsource` (forbidden by cycle-11 L1
in normal cases) because the test's purpose is to LINT the shipped form of
two distinct call sites in `compiler.py`. A behavioural test would need to
construct a divergence scenario the fix already prevents — i.e. would be
vacuous. Documented rationale: cycle-19 design.md AC14 DROP.
"""

from __future__ import annotations

import inspect


def test_prune_base_uses_canonical_rel_path_at_both_sites() -> None:
    """Both prune sites use the canonical helper or raw_dir.resolve().parent."""
    from kb.compile import compiler

    src = inspect.getsource(compiler)

    # Site 1 — `detect_source_drift` near line 270 uses the canonical helper.
    site1_present = (
        "_canonical_rel_path(s, raw_dir)" in src or "_canonical_rel_path(source, raw_dir)" in src
    )
    assert site1_present, (
        "Site 1 (detect_source_drift) must use _canonical_rel_path. If this "
        "assertion fails, the cycle-17 AC1 fix has been regressed. See "
        "docs/superpowers/decisions/2026-04-21-cycle19-design.md AC14 DROP rationale."
    )

    # Site 2 — `compile_wiki` full-mode tail prune near line 452 uses
    # `raw_dir.resolve().parent` to match the canonical helper's anchor.
    assert "raw_dir.resolve().parent" in src, (
        "Site 2 (compile_wiki full-mode prune base) must derive from "
        "raw_dir.resolve().parent. Cycle-17 AC1 shipped this fix; cycle-19 "
        "AC14 anchored it. Regression: see design.md AC14 DROP rationale."
    )


def test_manifest_key_for_alias_is_canonical_rel_path_at_module_scope() -> None:
    """manifest_key_for is the cycle-19 AC11 public alias; must remain a single source of truth."""
    from kb.compile.compiler import _canonical_rel_path, manifest_key_for

    # Identity check (not equality) — the alias must point at the same callable
    # so a refactor that copies-and-diverges cannot silently introduce a second
    # canonicalization path. R2 M1 / cycle-19 design.md AC11.
    assert manifest_key_for is _canonical_rel_path, (
        "manifest_key_for must be the IDENTITY alias of _canonical_rel_path "
        "(not a wrapper) — see cycle-19 design.md AC11."
    )
