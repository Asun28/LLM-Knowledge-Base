"""Cycle 23 AC4/AC5 — PEP 562 lazy-shim regression for kb.mcp.core.

Pins that a bare ``import kb.mcp`` does NOT pull heavy transitive deps
(anthropic, networkx, sentence-transformers, kb.query.engine,
kb.ingest.pipeline, kb.feedback.reliability). On first attribute access
via the module ``__getattr__`` the target module loads lazily and is
cached in the module globals — preserving the cycle-19 AC15 contract
that tests can ``monkeypatch.setattr(mcp_core.ingest_pipeline, ...)``.

The tests run as subprocesses so each probe starts with a fresh
sys.modules graph uncontaminated by prior pytest collection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"


def _run_probe(code: str, timeout: float = 10.0) -> dict:
    """Run ``code`` in a fresh subprocess with PYTHONPATH pointing at repo src.

    The probe must print a single JSON object on stdout and nothing else.
    """
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_REPO_SRC), os.environ.get("PYTHONPATH", "")]).rstrip(
            os.pathsep
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"probe failed (exit {proc.returncode}): {proc.stderr}")
    # Allow the probe to print other lines (e.g. warnings) before the JSON line;
    # pick the last non-empty stripped line as the payload.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(f"probe produced no output; stderr={proc.stderr!r}")
    return json.loads(lines[-1])


def test_bare_import_kb_mcp_does_not_pull_heavy_deps():
    """AC5 — `import kb.mcp` alone keeps heavy modules out of sys.modules.

    Cycle 26 AC2b / CONDITION 1 — allowlist extended to include
    ``kb.query.embeddings``. The cycle-26 warm-load wiring in
    ``kb.mcp.__init__.main()`` uses a FUNCTION-LOCAL import so a
    bare ``import kb.mcp`` still never pulls the embeddings module.
    Any future regression that hoists the import to module scope will
    trip this test.
    """
    code = (
        "import json, sys\n"
        "import kb.mcp  # noqa: F401 — smoke import for boot-leanness probe\n"
        "heavy = ['anthropic', 'networkx', 'sentence_transformers',\n"
        "         'kb.query.engine', 'kb.ingest.pipeline', 'kb.feedback.reliability',\n"
        "         'kb.query.embeddings']\n"
        "present = sorted(m for m in heavy if m in sys.modules)\n"
        "missing = sorted(m for m in heavy if m not in sys.modules)\n"
        "print(json.dumps({'present': present, 'missing': missing}))\n"
    )
    result = _run_probe(code)
    assert result["present"] == [], (
        f"cycle 23 AC4 + cycle 26 AC2b contract broken — bare `import kb.mcp` pulled: "
        f"{result['present']}"
    )
    assert set(result["missing"]) == {
        "anthropic",
        "networkx",
        "sentence_transformers",
        "kb.query.engine",
        "kb.ingest.pipeline",
        "kb.feedback.reliability",
        "kb.query.embeddings",
    }


def test_lazy_access_loads_module_and_is_identity_cached():
    """AC4 — first attribute access loads module; subsequent access returns same obj."""
    code = (
        "import json, sys\n"
        "from kb.mcp import core as c\n"
        "first = c.ingest_pipeline  # triggers lazy load\n"
        "import kb.ingest.pipeline as ip\n"
        "second = c.ingest_pipeline  # cached\n"
        "print(json.dumps({\n"
        "    'loaded': 'kb.ingest.pipeline' in sys.modules,\n"
        "    'identity_first': first is ip,\n"
        "    'identity_cached': first is second,\n"
        "    'attr_cached': 'ingest_pipeline' in c.__dict__,\n"
        "}))\n"
    )
    result = _run_probe(code)
    assert result["loaded"] is True
    assert result["identity_first"] is True, (
        "cycle-19 AC15 contract — mcp_core.ingest_pipeline must be kb.ingest.pipeline module"
    )
    assert result["identity_cached"] is True
    assert result["attr_cached"] is True, (
        "__getattr__ result should be cached in module globals to avoid re-lookup"
    )


def test_lazy_getattr_is_closed_allowlist():
    """AC4 — names not in _LAZY_MODULES raise AttributeError (closed shim).

    Threat I3 — ``__getattr__`` must NOT fall through to
    ``importlib.import_module(attacker_controlled)``. Use names that are
    definitely not in ``core`` module globals and not in ``_LAZY_MODULES``.
    """
    code = (
        "import json\n"
        "from kb.mcp import core\n"
        "probes = ['subprocess', 'xml_etree', 'ctypes', 'some_unknown_xyz']\n"
        "results = {}\n"
        "for name in probes:\n"
        "    try:\n"
        "        getattr(core, name)\n"
        "        results[name] = 'resolved'\n"
        "    except AttributeError:\n"
        "        results[name] = 'attr_error'\n"
        "print(json.dumps(results))\n"
    )
    result = _run_probe(code)
    assert all(v == "attr_error" for v in result.values()), (
        "PEP 562 __getattr__ must NOT fall through to arbitrary importlib — "
        f"closed allowlist guard failed for: {[k for k, v in result.items() if v != 'attr_error']}"
    )


def test_dir_reports_lazy_names():
    """AC4 — `dir(kb.mcp.core)` includes lazy names so introspection works."""
    code = (
        "import json\n"
        "from kb.mcp import core\n"
        "names = dir(core)\n"
        "lazy = ['ingest_pipeline', 'query_engine', 'reliability']\n"
        "print(json.dumps({'have': sorted(n for n in lazy if n in names)}))\n"
    )
    result = _run_probe(code)
    assert set(result["have"]) == {"ingest_pipeline", "query_engine", "reliability"}


def test_lazy_query_package_does_not_pull_engine_on_package_import():
    """AC4/Q9 — `import kb.query` alone should NOT load kb.query.engine."""
    code = (
        "import json, sys\n"
        "import kb.query  # noqa: F401\n"
        "print(json.dumps({\n"
        "    'engine_loaded': 'kb.query.engine' in sys.modules,\n"
        "}))\n"
    )
    result = _run_probe(code)
    assert result["engine_loaded"] is False, (
        "cycle-23 Q9 — kb.query package init must be PEP 562 lazy (mirror kb.ingest.__init__)"
    )


def test_lazy_query_attribute_access_loads_engine():
    """AC4/Q9 — `kb.query.query_wiki` attribute access triggers engine load."""
    code = (
        "import json, sys\n"
        "import kb.query\n"
        "qw = kb.query.query_wiki  # triggers lazy load\n"
        "print(json.dumps({\n"
        "    'engine_loaded': 'kb.query.engine' in sys.modules,\n"
        "    'is_callable': callable(qw),\n"
        "}))\n"
    )
    result = _run_probe(code)
    assert result["engine_loaded"] is True
    assert result["is_callable"] is True
