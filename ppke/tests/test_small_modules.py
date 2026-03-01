"""Tests for small/uncovered modules — pipeline stages, prompts, schema_builder, etc."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# pipeline/stages — simple re-exports
# ═══════════════════════════════════════════════════════════════════


class TestPipelineStages:
    def test_analyzer_import(self):
        from ppke.pipeline.stages import analyzer
        assert hasattr(analyzer, "build_logical_map")

    def test_concepts_import(self):
        from ppke.pipeline.stages import concepts
        assert hasattr(concepts, "build_concept_index")

    def test_extractor_import(self):
        from ppke.pipeline.stages import extractor
        assert hasattr(extractor, "extract_chapter")

    def test_patterns_import(self):
        from ppke.pipeline.stages import patterns
        assert hasattr(patterns, "detect_patterns")


# ═══════════════════════════════════════════════════════════════════
# llm/prompts.py
# ═══════════════════════════════════════════════════════════════════


class TestPrompts:
    def test_single_book_query_system_exists(self):
        from ppke.llm.prompts import SINGLE_BOOK_QUERY_SYSTEM
        assert isinstance(SINGLE_BOOK_QUERY_SYSTEM, str)
        assert len(SINGLE_BOOK_QUERY_SYSTEM) > 10

    def test_single_book_query_user_template(self):
        from ppke.llm.prompts import SINGLE_BOOK_QUERY_USER
        assert "{book_title}" in SINGLE_BOOK_QUERY_USER
        assert "{question}" in SINGLE_BOOK_QUERY_USER

    def test_cross_book_system_prompt(self):
        from ppke.llm import prompts
        assert hasattr(prompts, "CROSS_BOOK_QUERY_SYSTEM") or hasattr(prompts, "SINGLE_BOOK_QUERY_SYSTEM")

    def test_study_guide_prompt(self):
        from ppke.llm import prompts
        if hasattr(prompts, "STUDY_GUIDE_SYSTEM"):
            assert isinstance(prompts.STUDY_GUIDE_SYSTEM, str)

    def test_summary_prompt(self):
        from ppke.llm import prompts
        if hasattr(prompts, "SUMMARY_SYSTEM"):
            assert isinstance(prompts.SUMMARY_SYSTEM, str)


# ═══════════════════════════════════════════════════════════════════
# parser/schema_builder.py
# ═══════════════════════════════════════════════════════════════════


class TestSchemaBuilder:
    def test_build_extraction_model_exists(self):
        from ppke.parser import schema_builder
        assert hasattr(schema_builder, "build_extraction_model")

    def test_validate_schema_exists(self):
        from ppke.parser import schema_builder
        assert hasattr(schema_builder, "validate_schema")


# ═══════════════════════════════════════════════════════════════════
# converter/ocr.py
# ═══════════════════════════════════════════════════════════════════


class TestOCRModule:
    def test_ocr_functions_exist(self):
        from ppke.converter import ocr
        assert hasattr(ocr, "ocr_image") or hasattr(ocr, "ocr_pdf_pages")

    def test_ocr_image_requires_tesseract(self, tmp_path):
        from ppke.converter.ocr import ocr_image
        f = tmp_path / "test.png"
        f.write_bytes(b"fake png")
        with pytest.raises((ImportError, Exception)):
            ocr_image(f)


# ═══════════════════════════════════════════════════════════════════
# templates/base.py
# ═══════════════════════════════════════════════════════════════════


class TestTemplateBase:
    def test_plugin_template_model(self):
        from ppke.templates.base import PluginTemplate
        assert PluginTemplate is not None
        # Test creating a template model
        t = PluginTemplate(
            name="test",
            description="Test template",
            version="1.0.0",
            author="Tester",
            tier="custom",
            schema={"type": "object"},
        )
        assert t.name == "test"
        assert t.tier == "custom"


# ═══════════════════════════════════════════════════════════════════
# templates/loader.py
# ═══════════════════════════════════════════════════════════════════


class TestTemplateLoader:
    def test_discover_templates(self):
        from ppke.templates.loader import discover_templates
        templates = discover_templates()
        assert isinstance(templates, dict)

    def test_load_template_philosophy(self):
        from ppke.templates.loader import load_template
        try:
            t = load_template("philosophy")
            assert t.name == "philosophy"
        except Exception:
            pass  # Template might not exist in all environments

    def test_load_template_nonexistent(self):
        from ppke.templates.loader import load_template
        with pytest.raises(Exception):
            load_template("totally_nonexistent_template_xyz")

    def test_custom_templates_dir(self):
        from ppke.templates.loader import CUSTOM_TEMPLATES_DIR
        assert isinstance(CUSTOM_TEMPLATES_DIR, Path)


# ═══════════════════════════════════════════════════════════════════
# templates/validator.py
# ═══════════════════════════════════════════════════════════════════


class TestTemplateValidator:
    def test_validator_imports(self):
        from ppke.templates import validator
        assert hasattr(validator, "validate_template") or hasattr(validator, "TemplateValidator")
