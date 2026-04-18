def test_detect_source_drift_docstring_documents_deletion_pruning_persistence():
    from kb.compile.compiler import detect_source_drift

    assert "deletion-pruning" in detect_source_drift.__doc__
    assert "save_hashes=False" in detect_source_drift.__doc__


def test_wikilink_display_escape_preserves_pipe_via_backslash():
    from kb.utils.text import wikilink_display_escape

    assert wikilink_display_escape("A|B") == r"A\|B"
    assert wikilink_display_escape("plain title") == "plain title"
    assert wikilink_display_escape("A|B|C") == r"A\|B\|C"
