"""Cycle 66 AC4 — both-import-forms divergent-fail closure for T6.

`tests/_helpers/ast_walk.find_module_imports` MUST detect BOTH `ast.Import`
(bare form: `import diskcache`) AND `ast.ImportFrom` (from form: `from
diskcache import Cache`). If the helper silently regresses to from-form-only
detection — the cycle-66 root cause — this fixture goes RED for the
affected key in the affected module.

This is a per-module fixture, not a package-level scan: each parametrize
case writes a freshly-isolated tmp_path, so vacuous-green-on-revert is
structurally impossible regardless of what the production tree happens
to import. Generalises cycle-23 L2 / cycle-24 L4 vacuous-green class.
"""

import pytest

from tests._helpers.ast_walk import find_module_imports

CVE_BANNED_MODULES = ["diskcache", "litellm", "pip", "ragas"]


@pytest.mark.parametrize("module", CVE_BANNED_MODULES)
def test_both_import_forms_detected(module, tmp_path):
    """Per-module fixture writes both bare + from forms; helper must detect each.

    T6 closure: revert find_module_imports to ImportFrom-only detection and
    the `bare_file in result["import"]` assertion fires RED for every module.
    """
    bare_file = tmp_path / f"_test_only_bare_{module}.py"
    bare_file.write_text(f"import {module}\n")

    from_file = tmp_path / f"_test_only_from_{module}.py"
    from_file.write_text(f"from {module} import something\n")

    result = find_module_imports(module, src_root=tmp_path)

    assert bare_file in result["import"], (
        f"Bare-form `import {module}` not detected by find_module_imports. "
        f"Helper has regressed to from-form-only detection (cycle-66 T6)."
    )
    assert from_file in result["from"], (
        f"From-form `from {module} import X` not detected by "
        f"find_module_imports for module={module!r}."
    )
