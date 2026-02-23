"""Test suite for template system - Phase 4 validation."""

import pytest
from ppke.templates.loader import load_template, discover_templates
from ppke.parser.schema_builder import build_extraction_model
from ppke.templates.base import PluginTemplate


def test_discover_official_templates():
    """Ensure official templates (philosophy, legal) are discoverable."""
    templates = discover_templates()
    assert 'philosophy' in templates, "Philosophy template should be available"
    assert 'legal' in templates, "Legal template should be available"


def test_load_philosophy_template():
    """Validate philosophy template loads correctly with all required fields."""
    template = load_template('philosophy')
    assert template.name == 'philosophy'
    assert template.tier == 'official'
    assert len(template.stages) >= 4, "Philosophy template should have at least 4 stages"

    # Check that prompts are defined
    assert 'extraction' in template.prompts
    assert 'system' in template.prompts['extraction']
    assert 'user_template' in template.prompts['extraction']


def test_build_philosophy_model():
    """Test dynamic Pydantic model generation from philosophy schema."""
    template = load_template('philosophy')
    PhilosophyExtraction = build_extraction_model(template.schema['extraction_model'])

    result = PhilosophyExtraction(
        paragraph_id="{01}.p1",
        original_text="Test paragraph",
        topic_sentence="Summary of the test",
        function_in_argument="introduces thesis"
    )
    assert result.paragraph_id == "{01}.p1"
    assert result.function_in_argument == "introduces thesis"
    assert result.topic_sentence == "Summary of the test"


def test_legal_template():
    """Validate legal template loads and has legal-specific fields."""
    template = load_template('legal')
    assert template.name == 'legal'
    assert template.tier == 'official'

    LegalExtraction = build_extraction_model(template.schema['extraction_model'])

    result = LegalExtraction(
        paragraph_id="{01}.p1",
        original_text="Test legal text",
        topic_sentence="Summary of legal provision",
        legal_standard="strict scrutiny"
    )
    assert result.legal_standard == "strict scrutiny"


def test_template_has_required_stages():
    """Ensure templates have the required processing stages."""
    template = load_template('philosophy')

    stage_ids = [stage['id'] for stage in template.stages]
    required_stages = ['extraction', 'logical_map', 'concepts', 'patterns']

    for required in required_stages:
        assert required in stage_ids, f"Missing required stage: {required}"


def test_template_prompts_are_non_empty():
    """Ensure all template prompts have content."""
    template = load_template('philosophy')

    for prompt_name, prompt_data in template.prompts.items():
        if isinstance(prompt_data, dict):
            assert 'system' in prompt_data or 'user' in prompt_data, \
                f"Prompt {prompt_name} should have system or user messages"

            if 'system' in prompt_data:
                assert len(prompt_data['system']) > 0, \
                    f"Prompt {prompt_name} system message is empty"
            if 'user' in prompt_data:
                assert len(prompt_data['user']) > 0, \
                    f"Prompt {prompt_name} user message is empty"


def test_template_schema_has_required_fields():
    """Validate template schemas have required extraction model fields."""
    template = load_template('philosophy')

    assert 'extraction_model' in template.schema
    extraction_model = template.schema['extraction_model']

    # Schema has base_fields and fields
    # Check that the extraction model can be built
    model = build_extraction_model(extraction_model)
    model_fields = model.model_fields.keys()

    # Check for base required fields
    assert 'paragraph_id' in model_fields
    assert 'original_text' in model_fields
    assert 'topic_sentence' in model_fields


def test_template_outputs_defined():
    """Ensure templates have outputs field (may be empty)."""
    template = load_template('philosophy')

    # Outputs field exists (may be empty dict)
    assert template.outputs is not None
    assert isinstance(template.outputs, dict)


def test_multiple_templates_can_coexist():
    """Test that multiple templates can be loaded simultaneously."""
    phil_template = load_template('philosophy')
    legal_template = load_template('legal')

    # Both should be valid and distinct
    assert phil_template.name != legal_template.name
    assert phil_template.schema != legal_template.schema


def test_template_validation():
    """Test that loaded templates pass basic validation."""
    templates = discover_templates()

    for template_name in templates.keys():
        template = load_template(template_name)
        assert isinstance(template, PluginTemplate)
        assert template.name is not None
        assert len(template.name) > 0
        assert template.tier in ['official', 'community', 'custom']


def test_philosophy_extraction_model_fields():
    """Verify philosophy template has all v1.x required fields."""
    template = load_template('philosophy')
    model = build_extraction_model(template.schema['extraction_model'])

    # v1.x required fields for backward compatibility
    required_fields = [
        'paragraph_id',
        'original_text',
        'topic_sentence',
        'function_in_argument',
        'explicit_claims',
        'implicit_assumptions',
        'logical_steps',
        'emotional_tone',
        'tone_evidence'
    ]

    model_fields = model.model_fields.keys()
    for field in required_fields:
        assert field in model_fields, f"Missing v1.x field: {field}"


def test_legal_extraction_model_has_legal_fields():
    """Verify legal template has legal-specific fields."""
    template = load_template('legal')
    model = build_extraction_model(template.schema['extraction_model'])

    # Legal-specific fields
    legal_fields = [
        'legal_standard',
        'case_references',
        'statutory_citations'
    ]

    model_fields = model.model_fields.keys()
    for field in legal_fields:
        assert field in model_fields, f"Missing legal field: {field}"


def test_template_tier_classification():
    """Test that templates are correctly classified by tier."""
    philosophy = load_template('philosophy')
    legal = load_template('legal')

    assert philosophy.tier == 'official'
    assert legal.tier == 'official'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
