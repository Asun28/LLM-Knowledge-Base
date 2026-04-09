"""Phase 3.95 backlog fixes — v0.9.14."""

import pytest

# ── Task 1: Utils I/O and Path Safety ──


class TestAtomicJsonWriteFdSafety:
    """atomic_json_write must not leak the fd when open()/json.dump() raises."""

    def test_fd_closed_on_serialization_failure(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"

        class Unserializable:
            pass

        with pytest.raises(TypeError):
            atomic_json_write(Unserializable(), target)
        assert not target.exists()
        # Verify no leftover temp files
        assert not list(tmp_path.glob("*.tmp"))

    def test_successful_write_unchanged(self, tmp_path):
        from kb.utils.io import atomic_json_write

        target = tmp_path / "out.json"
        atomic_json_write({"key": "value"}, target)
        assert target.exists()
        import json

        assert json.loads(target.read_text(encoding="utf-8")) == {"key": "value"}


class TestMakeSourceRefLiteralRaw:
    """make_source_ref must always produce 'raw/...' prefix."""

    def test_custom_dir_name_still_uses_raw_prefix(self, tmp_path):
        from kb.utils.paths import make_source_ref

        custom_raw = tmp_path / "my_custom_raw_dir"
        articles = custom_raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=custom_raw)
        assert ref == "raw/articles/test.md"

    def test_standard_raw_dir_unchanged(self, tmp_path):
        from kb.utils.paths import make_source_ref

        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        source = articles / "test.md"
        source.write_text("content", encoding="utf-8")

        ref = make_source_ref(source, raw_dir=raw)
        assert ref == "raw/articles/test.md"
