"""Tests for v0.9.8 fixes — path traversal, structured outputs, dedup, atomic writes."""

import json
from unittest.mock import Mock, patch

import pytest

import kb.config

# ── 1. kb_ingest path traversal protection ──────────────────────────


class TestKbIngestPathTraversal:
    """kb_ingest must reject source paths outside the project directory."""

    def _patch_project(self, monkeypatch, tmp_path):
        """Set up a temporary project root for testing."""
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)
        raw = tmp_path / "raw" / "articles"
        raw.mkdir(parents=True)
        return raw

    def test_rejects_absolute_path_outside_project(self, tmp_path, monkeypatch):
        """Absolute path outside project root is rejected."""
        self._patch_project(monkeypatch, tmp_path)
        from kb.mcp.core import kb_ingest

        # Create a file outside the project
        outside = tmp_path.parent / "outside.md"
        outside.write_text("secret", encoding="utf-8")

        result = kb_ingest(source_path=str(outside))
        assert "Error:" in result
        assert "project directory" in result.lower()

    def test_rejects_relative_traversal(self, tmp_path, monkeypatch):
        """Relative path with .. escaping project root is rejected."""
        self._patch_project(monkeypatch, tmp_path)
        from kb.mcp.core import kb_ingest

        result = kb_ingest(source_path="../../etc/passwd")
        assert "Error:" in result
        # Should either say "project directory" or "not found"
        assert "Error:" in result

    def test_allows_valid_raw_path(self, tmp_path, monkeypatch):
        """Valid path within project root is allowed."""
        raw = self._patch_project(monkeypatch, tmp_path)
        from kb.mcp.core import kb_ingest

        source = raw / "valid-article.md"
        source.write_text("# Test Article\nContent here.", encoding="utf-8")

        # Without extraction_json, should return extraction prompt
        result = kb_ingest(
            source_path="raw/articles/valid-article.md",
            source_type="article",
        )
        assert "Error:" not in result or "not found" not in result.lower()

    def test_rejects_backslash_traversal(self, tmp_path, monkeypatch):
        """Path with backslash traversal is rejected."""
        self._patch_project(monkeypatch, tmp_path)
        from kb.mcp.core import kb_ingest

        result = kb_ingest(source_path="..\\..\\etc\\passwd")
        assert "Error:" in result

    def test_allows_absolute_path_inside_project(self, tmp_path, monkeypatch):
        """Absolute path within project root is allowed."""
        raw = self._patch_project(monkeypatch, tmp_path)
        from kb.mcp.core import kb_ingest

        source = raw / "abs-test.md"
        source.write_text("# Test\nContent.", encoding="utf-8")

        result = kb_ingest(
            source_path=str(source),
            source_type="article",
        )
        # Should not be a traversal error
        assert "project directory" not in result.lower()


# ── 2. Structured output extraction (call_llm_json) ─────────────────


class TestCallLlmJson:
    """call_llm_json uses tool_use for guaranteed structured output."""

    @pytest.fixture
    def mock_get_client(self):
        with patch("kb.utils.llm.get_client") as mock_gc:
            yield mock_gc

    def test_returns_tool_use_input(self, mock_get_client):
        """call_llm_json extracts input from tool_use content block."""
        from kb.utils.llm import call_llm_json

        tool_block = Mock(type="tool_use", input={"title": "Test", "score": 42})
        mock_get_client.return_value.messages.create.return_value = Mock(
            content=[tool_block]
        )

        result = call_llm_json(
            "Extract data",
            schema={"type": "object", "properties": {"title": {"type": "string"}}},
        )
        assert result == {"title": "Test", "score": 42}

    def test_raises_on_no_tool_use_block(self, mock_get_client):
        """call_llm_json raises LLMError if no tool_use block in response."""
        from kb.utils.llm import LLMError, call_llm_json

        text_block = Mock(type="text", text="Hello")
        mock_get_client.return_value.messages.create.return_value = Mock(
            content=[text_block]
        )

        with pytest.raises(LLMError, match="No tool_use block"):
            call_llm_json(
                "Extract data",
                schema={"type": "object", "properties": {}},
            )

    def test_invalid_tier_raises(self, mock_get_client):
        """call_llm_json raises ValueError for unknown tier."""
        from kb.utils.llm import call_llm_json

        with pytest.raises(ValueError, match="Invalid tier"):
            call_llm_json(
                "Extract data",
                tier="nonexistent",
                schema={"type": "object"},
            )

    def test_passes_tools_and_tool_choice(self, mock_get_client):
        """call_llm_json sends tools and forced tool_choice to the API."""
        from kb.utils.llm import call_llm_json

        tool_block = Mock(type="tool_use", input={"title": "OK"})
        mock_get_client.return_value.messages.create.return_value = Mock(
            content=[tool_block]
        )

        schema = {"type": "object", "properties": {"title": {"type": "string"}}}
        call_llm_json("Extract", schema=schema, tool_name="my_tool")

        call_kwargs = mock_get_client.return_value.messages.create.call_args.kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "my_tool"
        assert call_kwargs["tools"][0]["input_schema"] == schema
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "my_tool"}

    @patch("kb.utils.llm.time.sleep")
    def test_retries_on_rate_limit(self, mock_sleep, mock_get_client):
        """call_llm_json retries on rate limits then succeeds."""
        import anthropic

        from kb.utils.llm import call_llm_json

        tool_block = Mock(type="tool_use", input={"title": "OK"})
        mock_get_client.return_value.messages.create.side_effect = [
            anthropic.RateLimitError(
                message="rate limited",
                response=Mock(status_code=429, headers={}),
                body=None,
            ),
            Mock(content=[tool_block]),
        ]

        result = call_llm_json(
            "Extract",
            schema={"type": "object", "properties": {}},
        )
        assert result == {"title": "OK"}
        assert mock_sleep.called

    def test_system_prompt_passed(self, mock_get_client):
        """call_llm_json forwards system prompt to the API."""
        from kb.utils.llm import call_llm_json

        tool_block = Mock(type="tool_use", input={})
        mock_get_client.return_value.messages.create.return_value = Mock(
            content=[tool_block]
        )

        call_llm_json("Extract", schema={"type": "object"}, system="Be precise")
        call_kwargs = mock_get_client.return_value.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be precise"


# ── 3. Extraction schema builder ────────────────────────────────────


class TestBuildExtractionSchema:
    """build_extraction_schema builds valid JSON Schema from templates."""

    def test_article_template(self):
        """Article template produces schema with correct list/scalar types."""
        from kb.ingest.extractors import build_extraction_schema, load_template

        template = load_template("article")
        schema = build_extraction_schema(template)

        assert schema["type"] == "object"
        assert "title" in schema["properties"]
        assert "title" in schema["required"]
        # Scalar fields
        assert schema["properties"]["title"]["type"] == "string"
        assert schema["properties"]["author"]["type"] == "string"
        # List fields
        assert schema["properties"]["key_claims"]["type"] == "array"
        assert schema["properties"]["entities_mentioned"]["type"] == "array"
        assert schema["properties"]["concepts_mentioned"]["type"] == "array"

    def test_repo_template_name_required(self):
        """Repo template uses 'name' instead of 'title' — must be in required."""
        from kb.ingest.extractors import build_extraction_schema, load_template

        template = load_template("repo")
        schema = build_extraction_schema(template)

        assert "name" in schema["required"]
        assert "title" not in schema.get("required", [])

    def test_comparison_template_annotated_fields(self):
        """Comparison template with type annotations parses correctly."""
        import yaml

        from kb.config import TEMPLATES_DIR
        from kb.ingest.extractors import build_extraction_schema

        # Load comparison template directly (not a source type, so skip load_template)
        tpl = yaml.safe_load(
            (TEMPLATES_DIR / "comparison.yaml").read_text(encoding="utf-8")
        )
        schema = build_extraction_schema(tpl)

        assert "title" in schema["required"]
        assert schema["properties"]["subjects"]["type"] == "array"
        assert schema["properties"]["dimensions"]["type"] == "array"
        assert schema["properties"]["findings"]["type"] == "array"
        # title is a scalar despite annotation
        assert schema["properties"]["title"]["type"] == "string"

    def test_paper_template_list_fields(self):
        """Paper template correctly identifies list fields."""
        from kb.ingest.extractors import build_extraction_schema, load_template

        template = load_template("paper")
        schema = build_extraction_schema(template)

        assert schema["properties"]["authors"]["type"] == "array"
        assert schema["properties"]["key_claims"]["type"] == "array"
        assert schema["properties"]["title"]["type"] == "string"
        assert schema["properties"]["abstract"]["type"] == "string"


class TestParseFieldSpec:
    """_parse_field_spec handles both simple and annotated template formats."""

    def test_simple_field(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec("title")
        assert name == "title"
        assert desc == ""
        assert is_list is False

    def test_simple_field_with_comment(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec("key_claims           # List of claims")
        assert name == "key_claims"
        assert is_list is True  # known list field

    def test_annotated_string_field(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec(
            '"title (str): Title of the comparison"'
        )
        assert name == "title"
        assert desc == "Title of the comparison"
        assert is_list is False

    def test_annotated_list_field(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec(
            '"subjects (list[str]): Items being compared"'
        )
        assert name == "subjects"
        assert desc == "Items being compared"
        assert is_list is True

    def test_known_list_field(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec("entities_mentioned")
        assert name == "entities_mentioned"
        assert is_list is True

    def test_unknown_scalar_field(self):
        from kb.ingest.extractors import _parse_field_spec

        name, desc, is_list = _parse_field_spec("methodology")
        assert name == "methodology"
        assert is_list is False


# ── 4. Feedback deduplication ────────────────────────────────────────


class TestFeedbackDeduplication:
    """cited_pages must be deduplicated before trust score updates."""

    def test_duplicate_citations_counted_once(self, tmp_path):
        """Duplicate page IDs in cited_pages should only increment score once."""
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"

        # Add entry with duplicate citations
        add_feedback_entry(
            question="What is RAG?",
            rating="useful",
            cited_pages=["concepts/rag", "concepts/rag", "concepts/rag"],
            path=feedback_path,
        )

        # Load and verify trust score
        data = json.loads(feedback_path.read_text(encoding="utf-8"))
        scores = data["page_scores"]["concepts/rag"]
        assert scores["useful"] == 1  # Not 3
        # Trust with 1 useful: (1+1)/(1+0+2) = 2/3 ≈ 0.6667
        assert scores["trust"] == pytest.approx(0.6667, abs=0.001)

    def test_unique_citations_all_counted(self, tmp_path):
        """Different page IDs are all counted correctly."""
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"

        add_feedback_entry(
            question="Compare RAG vs fine-tuning",
            rating="useful",
            cited_pages=["concepts/rag", "concepts/fine-tuning"],
            path=feedback_path,
        )

        data = json.loads(feedback_path.read_text(encoding="utf-8"))
        assert "concepts/rag" in data["page_scores"]
        assert "concepts/fine-tuning" in data["page_scores"]
        assert data["page_scores"]["concepts/rag"]["useful"] == 1
        assert data["page_scores"]["concepts/fine-tuning"]["useful"] == 1


# ── 5. Atomic writes for review history ─────────────────────────────


class TestReviewHistoryAtomicWrite:
    """save_review_history must use atomic writes to prevent corruption."""

    def test_saves_history_file(self, tmp_path):
        """save_review_history creates a valid JSON file."""
        from kb.review.refiner import save_review_history

        history = [{"page_id": "concepts/rag", "status": "applied"}]
        path = tmp_path / "history.json"
        save_review_history(history, path)

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == history

    def test_no_temp_file_left_on_success(self, tmp_path):
        """Successful write leaves no .tmp files behind."""
        from kb.review.refiner import save_review_history

        path = tmp_path / "history.json"
        save_review_history([{"test": True}], path)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrites_existing_file(self, tmp_path):
        """save_review_history replaces existing content atomically."""
        from kb.review.refiner import save_review_history

        path = tmp_path / "history.json"
        save_review_history([{"v": 1}], path)
        save_review_history([{"v": 2}], path)

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == [{"v": 2}]

    def test_creates_parent_directories(self, tmp_path):
        """save_review_history creates parent dirs if they don't exist."""
        from kb.review.refiner import save_review_history

        path = tmp_path / "deep" / "nested" / "history.json"
        save_review_history([{"ok": True}], path)
        assert path.exists()


# ── 6. _make_api_call shared retry logic ─────────────────────────────


class TestMakeApiCall:
    """_make_api_call provides shared retry logic for call_llm and call_llm_json."""

    @pytest.fixture
    def mock_get_client(self):
        with patch("kb.utils.llm.get_client") as mock_gc:
            yield mock_gc

    def test_call_llm_still_works(self, mock_get_client):
        """call_llm returns text using shared _make_api_call."""
        from kb.utils.llm import call_llm

        mock_get_client.return_value.messages.create.return_value = Mock(
            content=[Mock(text="Hello")]
        )
        result = call_llm("Say hello", tier="write")
        assert result == "Hello"

    def test_call_llm_json_still_retries(self, mock_get_client):
        """call_llm_json retries via shared _make_api_call."""
        import anthropic

        from kb.utils.llm import call_llm_json

        tool_block = Mock(type="tool_use", input={"ok": True})
        mock_get_client.return_value.messages.create.side_effect = [
            anthropic.APIConnectionError(
                message="network error", request=Mock()
            ),
            Mock(content=[tool_block]),
        ]

        with patch("kb.utils.llm.time.sleep"):
            result = call_llm_json("Extract", schema={"type": "object"})
        assert result == {"ok": True}
