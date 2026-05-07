"""Cycle 67 AC04 — `KB_STRICT_PUBLISH=1` env var re-raises auto-publish failures.

Phase 4.5 MEDIUM: `auto_publish_after_compile` exceptions were swallowed,
making `compile_wiki` report success even when publish silently dropped.
A CI / release pipeline could not distinguish "compiled + published" from
"compiled but publish failed".

Cycle 67 AC04 adds `KB_STRICT_PUBLISH=1` (call-time read per cycle-19 L2):
- env unset → swallow + log.warning (default; back-compat with cycle 64)
- env="1"|"true"|"yes" (case-insensitive) → re-raise the publish exception

Truthiness convention matches AC06 `KB_DISABLE_VECTORS` per design FW-3
/ R1-C3 / C-AC04-truthy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import kb.compile.compiler as compiler_mod
import kb.compile.publish as publish_mod
from kb.compile.compiler import compile_wiki


def _make_minimal_wiki(tmp_path: Path) -> tuple[Path, Path]:
    """Set up a minimal wiki+raw tree so compile_wiki has something to do."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    (wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (raw / "articles").mkdir(parents=True, exist_ok=True)
    return wiki, raw


def _patch_publish_to_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force auto_publish_after_compile to raise. Patches the OWNER module
    so the function-local import in compiler.py resolves to the spy.

    Cycle-18 L1: function-local import `from kb.compile.publish import
    auto_publish_after_compile` resolves at call time via `kb.compile.publish`
    module attribute. Patching kb.compile.publish.auto_publish_after_compile
    reaches the call site.
    """

    def _raising_publish(*args, **kwargs):
        raise RuntimeError("simulated auto-publish failure for AC04")

    monkeypatch.setattr(publish_mod, "auto_publish_after_compile", _raising_publish)


def test_t04a_default_swallows_publish_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T04-A: env unset → publish raises but compile_wiki returns normally."""
    monkeypatch.delenv("KB_STRICT_PUBLISH", raising=False)
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)
    # Should NOT raise — exception is swallowed and logged.
    result = compile_wiki(wiki_dir=wiki, raw_dir=raw)
    assert isinstance(result, dict), "compile_wiki must return a dict"


def test_t04b_strict_one_reraises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T04-B: env=`"1"` → publish exception propagates to caller."""
    monkeypatch.setenv("KB_STRICT_PUBLISH", "1")
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)
    with pytest.raises(RuntimeError, match="simulated auto-publish failure"):
        compile_wiki(wiki_dir=wiki, raw_dir=raw)


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "TRUE", "Yes", "  yes  "])
def test_t04c_truthy_variants_enable_strict(
    truthy: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T04-C / C-AC04-truthy: each of {1, true, yes} (case-insensitive,
    whitespace-tolerant) enables strict mode."""
    monkeypatch.setenv("KB_STRICT_PUBLISH", truthy)
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)
    with pytest.raises(RuntimeError, match="simulated auto-publish failure"):
        compile_wiki(wiki_dir=wiki, raw_dir=raw)


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "anything-else"])
def test_t04c_falsy_variants_keep_default(
    falsy: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T04-C inverse: falsy / unrecognized values → default swallow behavior."""
    monkeypatch.setenv("KB_STRICT_PUBLISH", falsy)
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)
    # Should NOT raise.
    result = compile_wiki(wiki_dir=wiki, raw_dir=raw)
    assert isinstance(result, dict)


def test_t04d_call_time_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T04-D: env var read at CALL time per cycle-19 L2. Setting it after the
    first call mutates behavior on the second call WITHOUT process restart.
    """
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)

    # First call with env unset → swallows.
    monkeypatch.delenv("KB_STRICT_PUBLISH", raising=False)
    compile_wiki(wiki_dir=wiki, raw_dir=raw)  # no raise

    # Second call with env set → re-raises. Same process, no restart.
    monkeypatch.setenv("KB_STRICT_PUBLISH", "yes")
    with pytest.raises(RuntimeError, match="simulated auto-publish failure"):
        compile_wiki(wiki_dir=wiki, raw_dir=raw)


def test_t04e_compiler_module_loadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check that the compiler module's compile_wiki is the same
    object as the imported one, ensuring monkeypatch on publish_mod reaches
    the call site (cycle-18 L1 anchor)."""
    monkeypatch.delenv("KB_STRICT_PUBLISH", raising=False)
    wiki, raw = _make_minimal_wiki(tmp_path)
    _patch_publish_to_raise(monkeypatch)
    compile_wiki(wiki_dir=wiki, raw_dir=raw)
    assert compiler_mod.compile_wiki is compile_wiki
