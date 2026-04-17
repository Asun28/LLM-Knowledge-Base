"""Cycle 5 mechanical regression tests."""


def test_config_exports_verdict_validation_constants():
    from kb.config import VALID_SEVERITIES, VALID_VERDICT_TYPES

    assert VALID_SEVERITIES == ("error", "warning", "info")
    assert VALID_VERDICT_TYPES == (
        "fidelity",
        "consistency",
        "completeness",
        "review",
        "augment",
    )
