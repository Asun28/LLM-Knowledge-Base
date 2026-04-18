"""Cycle 9 compiler regression tests."""

import logging

from kb.compile import compiler


def test_load_manifest_recovers_from_os_error(tmp_path, monkeypatch, caplog):
    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text('{"raw/articles/test.md": "abc123"}', encoding="utf-8")

    original_read_text = compiler.Path.read_text

    def raise_oserror(self, *args, **kwargs):
        if self == manifest_path:
            raise OSError("disk read failed")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(compiler.Path, "read_text", raise_oserror)
    caplog.set_level(logging.WARNING, logger="kb.compile.compiler")

    result = compiler.load_manifest(manifest_path=manifest_path)

    assert result == {}
    assert any(
        str(manifest_path) in record.getMessage() and "disk read failed" in record.getMessage()
        for record in caplog.records
    )
