"""Cycle 64 — tests/conftest.py HIGH fixture leak surface (AC1–AC4).

Regression tests proving:
- AC1: autouse `tmp_kb_env` redirects `kb.config.WIKI_*` / `RAW_*` / `PROJECT_ROOT`
  to per-test `tmp_path` sandbox by default.
- AC2: `real_project_root` fixture raises `RuntimeError` without `--use-real-paths`.
- AC2: `real_project_root` fixture yields the real path WITH `--use-real-paths`.
- AC1.4: explicit-fixture call sites (existing 230+ tests requesting `tmp_kb_env`)
  still receive the same project Path on autouse promotion (non-regression).
- M1 / T2 mitigation: `WIKI_CONTRADICTIONS` write under autouse lands in tmp_path,
  not the real wiki tree.

Per cycle-40 L3 revert-verification: each behavioural test diverges expected vs
reverted behaviour. Reverting AC1 (drop the `autouse=True` decorator) makes
`test_default_isolation_redirects_wiki_constants_to_tmp` FAIL because tests that
don't request `tmp_kb_env` would see the real PROJECT_ROOT again.

Reverting AC2 (drop the `--use-real-paths` flag check) makes
`test_real_project_root_fixture_raises_without_flag` FAIL because the fixture
would yield instead of raise.

Cycle 64 AC4.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_default_isolation_redirects_wiki_constants_to_tmp(tmp_path):
    """AC1 + AC4: autouse `tmp_kb_env` redirects WIKI_* / RAW_* / PROJECT_ROOT.

    This test does NOT request `tmp_kb_env` explicitly. Under the autouse
    promotion (cycle 64 AC1), `kb.config.WIKI_DIR` etc. are nonetheless
    redirected to a tmp sandbox under the active `tmp_path`.

    Reverting the autouse decorator on `tmp_kb_env` (or removing the
    fixture entirely) would leave `kb.config.WIKI_DIR` pointing at the
    real repo wiki — this assertion would fail.
    """
    import kb.config as config  # noqa: PLC0415

    # The autouse fixture has set WIKI_DIR to a tmp_path-rooted location.
    # The test's tmp_path may not be IDENTICAL to the autouse fixture's
    # tmp_path (different fixture invocations) but BOTH must be under
    # pytest's per-test tmp root — so they share the same tmp grandparent.
    real_project_root = Path(__file__).resolve().parents[1]
    assert config.WIKI_DIR != real_project_root / "wiki", (
        "autouse tmp_kb_env did not redirect WIKI_DIR; reading the real wiki tree"
    )
    assert config.PROJECT_ROOT != real_project_root, (
        "autouse tmp_kb_env did not redirect PROJECT_ROOT; reading the real repo"
    )
    # Subdir constants from M1 / T2 must also be redirected (per tmp_kb_env's
    # 24-constant patch list — confirms the fixture covers the threat-model
    # subdir leak surface).
    assert config.WIKI_ENTITIES != real_project_root / "wiki" / "entities"
    assert config.WIKI_CONCEPTS != real_project_root / "wiki" / "concepts"
    assert config.RAW_ARTICLES != real_project_root / "raw" / "articles"


def test_default_isolation_writes_to_wiki_contradictions_land_in_tmp(tmp_path):
    """M1 / T2 mitigation: writing to `kb.config.WIKI_CONTRADICTIONS` lands
    inside per-test sandbox, NOT in the real wiki tree.

    This is the canonical Phase 4.5 R3 leak surface (referenced in
    requirements doc Cluster A + threat model M1).

    Reverting AC1 would let the write land at `<repo>/wiki/contradictions.md`
    and this test would observe a path under the real PROJECT_ROOT.
    """
    import kb.config as config  # noqa: PLC0415

    target = config.WIKI_CONTRADICTIONS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# CYCLE-64 sandbox check\n", encoding="utf-8")

    real_project_root = Path(__file__).resolve().parents[1]
    real_contradictions = real_project_root / "wiki" / "contradictions.md"
    # The write must NOT have landed at the real path.
    assert target != real_contradictions, (
        f"WIKI_CONTRADICTIONS unexpectedly resolved to real path: {target}"
    )
    # The target must be readable (write succeeded) under the sandbox.
    assert target.read_text(encoding="utf-8").startswith("# CYCLE-64 sandbox check")


def test_real_project_root_fixture_raises_without_flag(request):
    """AC2: `real_project_root` raises RuntimeError without `--use-real-paths`.

    Reverting AC2's flag check would let the fixture yield even without the
    flag, and this assertion would fail.
    """
    # Cycle 64 AC2: under default pytest invocation, request.getfixturevalue
    # for `real_project_root` raises a RuntimeError matching the documented
    # message substring.
    with pytest.raises(RuntimeError, match="--use-real-paths"):
        request.getfixturevalue("real_project_root")


def test_kb_sandbox_alias_resolves_to_tmp_kb_env(tmp_path, kb_sandbox):
    """AC1.4 / cycle 64: public `kb_sandbox` alias maps to the same fixture
    body as `tmp_kb_env`. Confirms the rename in `tests/conftest.py` does
    not regress the contract for either name.
    """
    # `kb_sandbox` is the public alias; `tmp_kb_env` is the original. Both
    # should yield a Path that is the per-test project sandbox.
    assert isinstance(kb_sandbox, Path)
    # The autouse `tmp_kb_env` runs FIRST; the explicit `kb_sandbox` request
    # binds to the SAME fixture body (alias == fixture object), so the
    # second invocation returns the same project path. (pytest deduplicates
    # by fixture object, so kb_sandbox and tmp_kb_env are one body.)
    assert kb_sandbox.exists()
    assert (kb_sandbox / "wiki").exists()
    assert (kb_sandbox / "raw").exists()
    assert (kb_sandbox / ".data").exists()


def test_real_project_root_fixture_yields_under_flag(request):
    """AC2: with `pytest --use-real-paths`, `real_project_root` yields the
    genuine repo PROJECT_ROOT and `tmp_kb_env` autouse early-returns so
    `kb.config.PROJECT_ROOT` is unmodified.

    Without the flag, `real_project_root` raises RuntimeError (covered by
    the previous test); this test SKIPs in that case so default `pytest`
    invocations stay green, and only EXERCISES the yield path when the
    flag is explicitly passed.

    Reverting AC2's `--use-real-paths` opt-out branch in `tmp_kb_env` would
    leave the autouse monkeypatch in place even with the flag, and the
    `config.PROJECT_ROOT == real_root` assertion below would fail under
    `pytest --use-real-paths`.
    """
    import kb.config as config  # noqa: PLC0415

    try:
        real_root = request.getfixturevalue("real_project_root")
    except RuntimeError as exc:
        if "--use-real-paths" in str(exc):
            pytest.skip(
                "Yield-path verification requires `pytest --use-real-paths`; "
                "raise-path coverage is in test_real_project_root_fixture_raises_without_flag"
            )
        raise

    assert real_root.exists(), f"real_project_root yielded non-existent path: {real_root}"
    assert (real_root / "CLAUDE.md").exists(), (
        f"real_project_root does not look like the project root (no CLAUDE.md): {real_root}"
    )
    assert config.PROJECT_ROOT == real_root, (
        "tmp_kb_env did NOT early-return under --use-real-paths; "
        f"config.PROJECT_ROOT={config.PROJECT_ROOT}, real={real_root}"
    )
