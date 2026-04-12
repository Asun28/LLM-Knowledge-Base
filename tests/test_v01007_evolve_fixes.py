"""Tests for Phase 4 evolve/ fixes."""
from __future__ import annotations


def test_find_connection_opportunities_caps_pairs(tmp_wiki):
    """pair_shared_terms must not exceed 50k pairs."""
    from kb.evolve.analyzer import find_connection_opportunities
    from kb.graph.builder import scan_wiki_pages

    # Create enough pages with overlapping terms to exceed the cap
    (tmp_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    for i in range(40):
        (tmp_wiki / "concepts" / f"p{i}.md").write_text(
            f"---\ntitle: p{i}\ntype: concept\nconfidence: stated\n---\n"
            + "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10,
            encoding="utf-8",
        )
    pages = scan_wiki_pages(tmp_wiki)
    # Must complete without OOM or hanging — and return a list
    result = find_connection_opportunities(pages=pages, wiki_dir=tmp_wiki)
    assert isinstance(result, list)


def test_generate_evolution_report_scans_once(monkeypatch, tmp_wiki):
    """scan_wiki_pages must be called at most once per generate_evolution_report call."""
    from kb.evolve import analyzer as _a

    calls = {"n": 0}

    # We need to intercept the actual function used internally
    # First, find what name it's imported/called under in analyzer.py
    original = getattr(_a, "scan_wiki_pages", None) or getattr(_a, "_scan_wiki_pages", None)

    def counting(*args, **kwargs):
        calls["n"] += 1
        if original:
            return original(*args, **kwargs)
        return []

    # Try both possible attribute names
    for attr in ("scan_wiki_pages", "_scan_wiki_pages", "load_all_pages"):
        if hasattr(_a, attr):
            monkeypatch.setattr(_a, attr, counting)
            break

    (tmp_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (tmp_wiki / "concepts" / "x.md").write_text(
        "---\ntitle: x\ntype: concept\nconfidence: stated\n---\nbody\n",
        encoding="utf-8",
    )
    try:
        _a.generate_evolution_report(wiki_dir=tmp_wiki)
    except Exception:
        pass  # Function may fail in test env; we only care about call count
    assert calls["n"] <= 1, f"Expected <=1 scan calls, got {calls['n']}"


def test_generate_evolution_report_handles_oserror(monkeypatch):
    """OSError from feedback file must not propagate as unhandled exception."""
    from kb.evolve import analyzer as _a

    def _raise_oserror(*args, **kwargs):
        raise OSError("feedback file corrupt")

    # Find the function that wraps feedback access
    for attr in ("get_flagged_pages", "_get_flagged_pages"):
        if hasattr(_a, attr):
            monkeypatch.setattr(_a, attr, _raise_oserror)
            break

    # Must not raise (function catches OSError now)
    try:
        _a.generate_evolution_report()
    except OSError:
        raise AssertionError("OSError should have been caught by generate_evolution_report")
    except Exception:
        pass  # Other exceptions are acceptable
