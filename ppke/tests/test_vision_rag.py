"""Tests for ppke.pipeline.vision_rag — Vision-RAG pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# VisualElement model
# ═══════════════════════════════════════════════════════════════════


class TestVisualElement:
    def test_basic_construction(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(
            source_path="/path/to/figure.png",
            visual_type="diagram",
            title="System Architecture",
            description="A diagram showing the system architecture.",
            extracted_data={
                "entities": ["Frontend", "Backend", "Database"],
                "relationships": ["Frontend connects to Backend", "Backend queries Database"],
            },
            conclusions=["The system uses a three-tier architecture."],
            context_summary="System architecture diagram with three-tier layout.",
        )
        assert elem.visual_type == "diagram"
        assert elem.title == "System Architecture"
        assert len(elem.extracted_data["entities"]) == 3
        assert len(elem.conclusions) == 1

    def test_element_id(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(source_path="/img/fig1.png")
        assert elem.element_id == "visual_fig1"

        elem_with_page = VisualElement(source_path="/img/fig2.png", source_page=3)
        assert elem_with_page.element_id == "visual_fig2_p3"

    def test_to_rag_text_full(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(
            source_path="/img/chart.png",
            visual_type="chart",
            title="Revenue Growth",
            description="Bar chart showing revenue growth over 5 years.",
            extracted_data={
                "entities": ["2019", "2020", "2021"],
                "relationships": ["Revenue increased year-over-year"],
                "data_points": ["2019: $1M", "2020: $1.5M"],
                "text_content": ["Revenue (USD)", "Year"],
            },
            conclusions=["Revenue grew 50% from 2019 to 2020."],
            context_summary="Revenue growth bar chart spanning 2019-2021.",
        )
        rag_text = elem.to_rag_text()
        assert "[CHART]" in rag_text
        assert "Revenue Growth" in rag_text
        assert "2019" in rag_text
        assert "Revenue grew" in rag_text
        assert "Revenue (USD)" in rag_text

    def test_to_rag_text_minimal(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(source_path="/img/unknown.png")
        rag_text = elem.to_rag_text()
        assert "unknown.png" in rag_text

    def test_to_rag_text_empty_data(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(
            source_path="/img/test.png",
            title="Test",
            visual_type="figure",
        )
        rag_text = elem.to_rag_text()
        assert "[FIGURE]" in rag_text
        assert "Test" in rag_text

    def test_defaults(self):
        from ppke.pipeline.vision_rag import VisualElement

        elem = VisualElement(source_path="/img/test.png")
        assert elem.visual_type == "other"
        assert elem.title == ""
        assert elem.description == ""
        assert elem.extracted_data == {}
        assert elem.conclusions == []
        assert elem.source_page is None


# ═══════════════════════════════════════════════════════════════════
# _parse_analysis_response
# ═══════════════════════════════════════════════════════════════════


class TestParseAnalysisResponse:
    def test_valid_json(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        raw = json.dumps({
            "visual_type": "table",
            "title": "Results",
            "description": "A results table.",
        })
        result = _parse_analysis_response(raw)
        assert result["visual_type"] == "table"
        assert result["title"] == "Results"

    def test_json_with_markdown_fences(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        raw = '```json\n{"visual_type": "diagram", "title": "Flow"}\n```'
        result = _parse_analysis_response(raw)
        assert result["visual_type"] == "diagram"

    def test_json_with_plain_fences(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        raw = '```\n{"visual_type": "chart"}\n```'
        result = _parse_analysis_response(raw)
        assert result["visual_type"] == "chart"

    def test_json_embedded_in_text(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        raw = 'Here is the analysis:\n{"visual_type": "figure", "title": "Test"}\nDone.'
        result = _parse_analysis_response(raw)
        assert result["visual_type"] == "figure"

    def test_invalid_json_returns_empty(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        result = _parse_analysis_response("not json at all")
        assert result == {}

    def test_empty_string_returns_empty(self):
        from ppke.pipeline.vision_rag import _parse_analysis_response

        result = _parse_analysis_response("")
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# analyze_image
# ═══════════════════════════════════════════════════════════════════


class TestAnalyzeImage:
    def test_file_not_found(self, tmp_path):
        from ppke.pipeline.vision_rag import analyze_image

        with pytest.raises(FileNotFoundError):
            analyze_image(tmp_path / "nonexistent.png")

    def test_unsupported_format(self, tmp_path):
        from ppke.pipeline.vision_rag import analyze_image

        f = tmp_path / "test.xyz"
        f.write_bytes(b"data")
        with pytest.raises(ValueError, match="Unsupported image format"):
            analyze_image(f)

    @patch("ppke.pipeline.vision_rag._call_vision_llm")
    def test_successful_analysis(self, mock_llm, tmp_path):
        from ppke.pipeline.vision_rag import analyze_image

        mock_llm.return_value = json.dumps({
            "visual_type": "flowchart",
            "title": "Decision Process",
            "description": "A flowchart showing the decision-making process.",
            "extracted_data": {
                "entities": ["Start", "Decision", "End"],
                "relationships": ["Start leads to Decision", "Decision leads to End"],
                "data_points": [],
                "text_content": ["Yes", "No"],
            },
            "conclusions": ["The process has a single decision point."],
            "context_summary": "Flowchart with one decision node.",
        })

        img = tmp_path / "flowchart.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        elem = analyze_image(img, provider="anthropic")
        assert elem.visual_type == "flowchart"
        assert elem.title == "Decision Process"
        assert "Start" in elem.extracted_data["entities"]
        assert len(elem.conclusions) == 1
        mock_llm.assert_called_once()

    @patch("ppke.pipeline.vision_rag._call_vision_llm")
    def test_analysis_with_source_page(self, mock_llm, tmp_path):
        from ppke.pipeline.vision_rag import analyze_image

        mock_llm.return_value = json.dumps({"visual_type": "table"})

        img = tmp_path / "table.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)

        elem = analyze_image(img, provider="anthropic", source_page=5)
        assert elem.source_page == 5
        assert elem.element_id == "visual_table_p5"

    @patch("ppke.pipeline.vision_rag._call_vision_llm")
    def test_analysis_llm_failure_returns_minimal(self, mock_llm, tmp_path):
        from ppke.pipeline.vision_rag import analyze_image

        mock_llm.side_effect = Exception("API error")

        img = tmp_path / "broken.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)

        elem = analyze_image(img, provider="anthropic")
        assert elem.visual_type == "other"
        assert elem.title == "broken"  # Falls back to filename stem
        assert elem.source_path == str(img)


# ═══════════════════════════════════════════════════════════════════
# analyze_document_visuals
# ═══════════════════════════════════════════════════════════════════


class TestAnalyzeDocumentVisuals:
    def test_not_a_directory(self, tmp_path):
        from ppke.pipeline.vision_rag import analyze_document_visuals

        result = analyze_document_visuals(tmp_path / "nonexistent")
        assert result == []

    def test_empty_directory(self, tmp_path):
        from ppke.pipeline.vision_rag import analyze_document_visuals

        empty_dir = tmp_path / "figures"
        empty_dir.mkdir()
        result = analyze_document_visuals(empty_dir)
        assert result == []

    def test_no_image_files(self, tmp_path):
        from ppke.pipeline.vision_rag import analyze_document_visuals

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "readme.txt").write_text("not an image")
        result = analyze_document_visuals(fig_dir)
        assert result == []

    @patch("ppke.pipeline.vision_rag._call_vision_llm")
    def test_multiple_images(self, mock_llm, tmp_path):
        from ppke.pipeline.vision_rag import analyze_document_visuals

        mock_llm.return_value = json.dumps({
            "visual_type": "figure",
            "title": "Test Figure",
            "description": "A test figure.",
        })

        fig_dir = tmp_path / "figures"
        fig_dir.mkdir()
        (fig_dir / "fig1.png").write_bytes(b"\x89PNG" + b"\x00" * 50)
        (fig_dir / "fig2.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)
        (fig_dir / "notes.txt").write_text("not an image")

        result = analyze_document_visuals(fig_dir, provider="anthropic")
        assert len(result) == 2
        assert all(e.visual_type == "figure" for e in result)
        assert mock_llm.call_count == 2


# ═══════════════════════════════════════════════════════════════════
# build_visual_context
# ═══════════════════════════════════════════════════════════════════


class TestBuildVisualContext:
    def test_empty_list(self):
        from ppke.pipeline.vision_rag import build_visual_context

        assert build_visual_context([]) == ""

    def test_single_element(self):
        from ppke.pipeline.vision_rag import VisualElement, build_visual_context

        elem = VisualElement(
            source_path="/img/fig.png",
            visual_type="diagram",
            title="Architecture",
            description="System architecture diagram.",
            extracted_data={
                "entities": ["A", "B"],
                "relationships": ["A connects to B"],
                "data_points": ["latency: 10ms"],
            },
            conclusions=["Low latency design."],
        )
        ctx = build_visual_context([elem])
        assert "## Visual Elements Analysis" in ctx
        assert "### Visual 1: Architecture" in ctx
        assert "**Type:** diagram" in ctx
        assert "System architecture diagram." in ctx
        assert "A, B" in ctx
        assert "A connects to B" in ctx
        assert "latency: 10ms" in ctx
        assert "Low latency design." in ctx

    def test_multiple_elements(self):
        from ppke.pipeline.vision_rag import VisualElement, build_visual_context

        elems = [
            VisualElement(
                source_path="/img/fig1.png",
                visual_type="table",
                title="Results Table",
            ),
            VisualElement(
                source_path="/img/fig2.png",
                visual_type="chart",
                title="Trend Chart",
                description="A chart showing trends.",
            ),
        ]
        ctx = build_visual_context(elems)
        assert "### Visual 1: Results Table" in ctx
        assert "### Visual 2: Trend Chart" in ctx
        assert "**Type:** table" in ctx
        assert "**Type:** chart" in ctx


# ═══════════════════════════════════════════════════════════════════
# _call_vision_llm
# ═══════════════════════════════════════════════════════════════════


class TestCallVisionLLM:
    def test_unsupported_provider(self, tmp_path):
        from ppke.pipeline.vision_rag import _call_vision_llm

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)

        with pytest.raises(ValueError, match="not supported"):
            _call_vision_llm(img, provider="unsupported")

    def test_anthropic_provider(self, tmp_path):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text='{"visual_type": "figure"}')]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.Anthropic.return_value = mock_client

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            from ppke.pipeline.vision_rag import _call_vision_llm
            result = _call_vision_llm(img, provider="anthropic", api_key="test-key")

        assert result == '{"visual_type": "figure"}'
        mock_anthropic.Anthropic.assert_called_once_with(api_key="test-key")

    def test_openai_provider(self, tmp_path):
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.message.content = '{"visual_type": "table"}'
        mock_resp = MagicMock()
        mock_resp.choices = [mock_msg]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai.OpenAI.return_value = mock_client

        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from ppke.pipeline.vision_rag import _call_vision_llm
            result = _call_vision_llm(img, provider="openai", api_key="test-key")

        assert result == '{"visual_type": "table"}'
        mock_openai.OpenAI.assert_called_once_with(api_key="test-key")


# ═══════════════════════════════════════════════════════════════════
# VectorStore.index_visual_elements
# ═══════════════════════════════════════════════════════════════════


class TestVectorStoreVisualIndex:
    def test_index_visual_elements_unavailable(self, tmp_path):
        """When ChromaDB is not available, indexing returns 0."""
        from ppke.vectordb.store import VectorStore

        with patch("ppke.vectordb.store._chroma_available", False):
            store = VectorStore(tmp_path)
            result = store.index_visual_elements(
                book_folder="Book_Test",
                book_title="Test",
                author="Author",
                visual_elements=[],
            )
            assert result == 0

    def test_index_visual_elements_with_objects(self, tmp_path):
        """Test indexing VisualElement objects."""
        from ppke.pipeline.vision_rag import VisualElement
        from ppke.vectordb.store import VectorStore

        mock_collection = MagicMock()
        store = VectorStore.__new__(VectorStore)
        store._vault_path = tmp_path
        store._db_path = tmp_path / ".vector_db"
        store._client = MagicMock()
        store._collection = mock_collection

        elements = [
            VisualElement(
                source_path="/img/fig1.png",
                visual_type="diagram",
                title="Architecture",
                description="System architecture.",
                context_summary="Architecture diagram.",
            ),
            VisualElement(
                source_path="/img/fig2.png",
                visual_type="table",
                title="Results",
                description="Results table.",
                context_summary="Results table.",
            ),
        ]

        with patch("ppke.vectordb.store._chroma_available", True):
            result = store.index_visual_elements(
                book_folder="Book_Test",
                book_title="Test Book",
                author="Test Author",
                visual_elements=elements,
            )

        assert result == 2
        mock_collection.upsert.assert_called_once()
        call_args = mock_collection.upsert.call_args
        assert len(call_args.kwargs["documents"]) == 2
        assert "visual_diagram" in call_args.kwargs["metadatas"][0]["function_in_argument"]

    def test_index_visual_elements_empty_list(self, tmp_path):
        """Test that empty list returns 0."""
        from ppke.vectordb.store import VectorStore

        store = VectorStore.__new__(VectorStore)
        store._vault_path = tmp_path
        store._db_path = tmp_path / ".vector_db"
        store._client = MagicMock()
        store._collection = MagicMock()

        with patch("ppke.vectordb.store._chroma_available", True):
            result = store.index_visual_elements(
                book_folder="Book_Test",
                book_title="Test",
                author="Author",
                visual_elements=[],
            )

        assert result == 0

    def test_index_visual_elements_deduplication(self, tmp_path):
        """Test that duplicate element IDs are deduplicated."""
        from ppke.pipeline.vision_rag import VisualElement
        from ppke.vectordb.store import VectorStore

        mock_collection = MagicMock()
        store = VectorStore.__new__(VectorStore)
        store._vault_path = tmp_path
        store._db_path = tmp_path / ".vector_db"
        store._client = MagicMock()
        store._collection = mock_collection

        # Two elements with the same source path → same element_id
        elements = [
            VisualElement(
                source_path="/img/fig.png",
                visual_type="diagram",
                title="Version 1",
                description="First version.",
            ),
            VisualElement(
                source_path="/img/fig.png",
                visual_type="diagram",
                title="Version 2",
                description="Second version.",
            ),
        ]

        with patch("ppke.vectordb.store._chroma_available", True):
            result = store.index_visual_elements(
                book_folder="Book_Test",
                book_title="Test",
                author="Author",
                visual_elements=elements,
            )

        # Only the first should be indexed
        assert result == 1
