from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_augment_package_structure_cycle44() -> None:
    pkg = ROOT / "src" / "kb" / "lint" / "augment"
    assert pkg.is_dir()
    for module in (
        "collector",
        "proposer",
        "fetcher",
        "persister",
        "quality",
        "manifest",
        "rate",
        "orchestrator",
        "__init__",
    ):
        assert (pkg / f"{module}.py").is_file(), f"M2: {module}.py missing"
    assert not (ROOT / "src" / "kb" / "lint" / "augment.py").exists()
    # Cycle 46 — Phase 4.6 LOW closeout: legacy `_augment_*.py` compat shims deleted
    # (deferred from cycle 44 → 45 → 46). Both file presence AND importability are
    # pinned per CONDITION 2 / `feedback_test_behavior_over_signature` / C40-L3 —
    # `is_file()` covers disk state; `pytest.raises(ModuleNotFoundError)` is the
    # behavioural contract. Either failure flags a partial cycle-46 revert.
    assert not (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()
    assert not (ROOT / "src" / "kb" / "lint" / "_augment_rate.py").is_file()
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_manifest  # noqa: F401
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_rate  # noqa: F401


def test_augment_package_reexports_match_former_flat_symbols_cycle44() -> None:
    import kb.lint.augment
    from kb.lint.augment import (
        _build_proposer_prompt,
        _format_proposals_md,
        _parse_proposals_md,
        _post_ingest_quality,
        _propose_urls,
        _record_verdict_gap_callout,
        _relevance_score,
        _resolve_raw_dir,
        run_augment,
    )

    assert run_augment is kb.lint.augment.orchestrator.run_augment
    assert _build_proposer_prompt is kb.lint.augment.proposer._build_proposer_prompt
    assert _relevance_score is kb.lint.augment.proposer._relevance_score
    assert _propose_urls is kb.lint.augment.proposer._propose_urls
    assert _format_proposals_md is kb.lint.augment.persister._format_proposals_md
    assert _parse_proposals_md is kb.lint.augment.persister._parse_proposals_md
    assert _post_ingest_quality is kb.lint.augment.quality._post_ingest_quality
    assert _resolve_raw_dir is kb.lint.augment.quality._resolve_raw_dir
    assert _record_verdict_gap_callout is kb.lint.augment.quality._record_verdict_gap_callout


def test_augment_package_imports_with_nonexistent_wiki_dir_cycle44(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_path / "nonexistent" / "wiki")
    import kb.lint.augment.manifest
    import kb.lint.augment.rate

    importlib.reload(kb.lint.augment.manifest)
    importlib.reload(kb.lint.augment.rate)

    assert hasattr(kb.lint.augment.manifest, "Manifest")
    assert hasattr(kb.lint.augment.rate, "RateLimiter")


def test_run_augment_docstring_survives_cycle46_import_flip() -> None:
    """CONDITION 3 forward-protection — `run_augment.__doc__` must keep the
    `"Three-gate"` marker even after the AC3 import flip. Catches any future
    edit that orphans the docstring per cycle-23 L1 (function-local imports
    placed BEFORE the closing triple-quote)."""
    from kb.lint.augment.orchestrator import run_augment

    assert run_augment.__doc__ is not None
    assert "Three-gate" in run_augment.__doc__
