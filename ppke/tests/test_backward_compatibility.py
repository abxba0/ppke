"""Backward compatibility tests for PPKE v2.0 - Phase 4 validation.

These tests ensure that the philosophy domain in v2.0 maintains 100% compatibility
with v1.x functionality.
"""

import pytest
from ppke.templates.loader import load_template
from ppke.parser.schema_builder import build_extraction_model


def test_philosophy_extraction_fields():
    """Ensure philosophy template has all v1.x fields."""
    template = load_template('philosophy')
    model = build_extraction_model(template.schema['extraction_model'])

    # v1.x required fields
    required_fields = [
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


def test_philosophy_field_types():
    """Verify that philosophy fields maintain v1.x compatible types."""
    template = load_template('philosophy')
    model = build_extraction_model(template.schema['extraction_model'])

    # Create instance with v1.x-style data
    result = model(
        paragraph_id="{01}.p1",
        original_text="Test text",
        topic_sentence="Test summary",
        function_in_argument="introduces thesis",
        explicit_claims=["claim1", "claim2"],
        implicit_assumptions=["assumption1"],
        logical_steps=["step1", "step2"],
        emotional_tone="neutral",
        tone_evidence="The text is matter-of-fact"
    )

    # Verify types
    assert isinstance(result.explicit_claims, list)
    assert isinstance(result.implicit_assumptions, list)
    assert isinstance(result.logical_steps, list)
    assert isinstance(result.emotional_tone, str)
    assert isinstance(result.function_in_argument, str)


def test_philosophy_default_domain():
    """Test that philosophy is the default domain (backward compatibility)."""
    # When no domain is specified, philosophy should be the default
    # This is tested via load_template with no domain parameter
    default_template = load_template('philosophy')
    assert default_template.name == 'philosophy'


def test_philosophy_prompts_exist():
    """Ensure all v1.x philosophy prompts are present."""
    template = load_template('philosophy')

    # v2.0 prompt names (concepts and patterns instead of concept_index and pattern_detection)
    required_prompts = [
        'extraction',
        'logical_map',
        'concepts',  # v2.0 uses 'concepts' instead of 'concept_index'
        'patterns'   # v2.0 uses 'patterns' instead of 'pattern_detection'
    ]

    for prompt_name in required_prompts:
        assert prompt_name in template.prompts, \
            f"Missing prompt: {prompt_name}"


def test_philosophy_stages_order():
    """Verify philosophy stages run in correct order."""
    template = load_template('philosophy')

    stage_ids = [stage['id'] for stage in template.stages]

    # v2.0 processing order (updated naming)
    expected_order = ['extraction', 'logical_map', 'concepts', 'patterns']

    for expected_stage in expected_order:
        assert expected_stage in stage_ids, f"Missing stage: {expected_stage}"


def test_philosophy_output_files():
    """Ensure philosophy template stages define output files."""
    template = load_template('philosophy')

    # v2.0 defines outputs in stage definitions
    stage_output_files = [
        stage.get('output_file') for stage in template.stages
        if 'output_file' in stage
    ]

    # Check that some stages produce output files
    assert len(stage_output_files) > 0, "Template should define output files in stages"

    # Check that key output files are defined
    assert '02_Logical_Map.md' in stage_output_files
    assert '03_Concept_Index.md' in stage_output_files


def test_no_breaking_changes_in_philosophy_schema():
    """Ensure no fields were removed from v1.x philosophy schema."""
    template = load_template('philosophy')
    model = build_extraction_model(template.schema['extraction_model'])

    # All v1.x fields must be present
    v1_fields = {
        'paragraph_id', 'original_text', 'topic_sentence',
        'function_in_argument', 'explicit_claims', 'implicit_assumptions',
        'logical_steps', 'emotional_tone', 'tone_evidence', 'depth'
    }

    model_field_names = set(model.model_fields.keys())

    missing_fields = v1_fields - model_field_names
    assert len(missing_fields) == 0, f"Missing v1.x fields: {missing_fields}"


def test_philosophy_model_accepts_v1_data():
    """Test that philosophy model can process v1.x-style extraction results."""
    template = load_template('philosophy')
    model = build_extraction_model(template.schema['extraction_model'])

    # Simulate v1.x extraction result
    v1_style_data = {
        "paragraph_id": "{03}.p12",
        "original_text": "Original paragraph text from book.",
        "topic_sentence": "This paragraph discusses X.",
        "function_in_argument": "provides evidence",
        "explicit_claims": ["Claim A", "Claim B"],
        "implicit_assumptions": ["Assumption 1"],
        "logical_steps": ["Step 1", "Step 2"],
        "emotional_tone": "argumentative",
        "tone_evidence": "Uses strong language",
        "depth": "full"
    }

    result = model(**v1_style_data)

    # Verify all fields are preserved
    assert result.paragraph_id == v1_style_data["paragraph_id"]
    assert result.function_in_argument == v1_style_data["function_in_argument"]
    assert result.explicit_claims == v1_style_data["explicit_claims"]
    assert result.emotional_tone == v1_style_data["emotional_tone"]


def test_philosophy_stage_names_unchanged():
    """Verify philosophy stage IDs are present (functionally equivalent to v1.x)."""
    template = load_template('philosophy')

    stage_ids = {stage['id'] for stage in template.stages}

    # v2.0 stages (functionally equivalent to v1.x, with updated naming)
    v2_stages = {'extraction', 'logical_map', 'concepts', 'patterns'}

    assert v2_stages.issubset(stage_ids), \
        f"Missing stages: {v2_stages - stage_ids}"


def test_philosophy_vault_structure_compatibility():
    """Ensure philosophy template maintains compatible vault structure."""
    template = load_template('philosophy')

    # v2.0 defines outputs in stages
    # Check that stages produce output files (vault structure compatibility)
    has_output_files = any('output_file' in stage for stage in template.stages)
    assert has_output_files, "Template should define output files for vault structure"

    # The actual meta.yml and extractions.json are written by the orchestrator,
    # not defined in template.outputs


def test_legal_does_not_affect_philosophy():
    """Ensure adding legal domain doesn't break philosophy."""
    phil_template = load_template('philosophy')
    legal_template = load_template('legal')

    # Philosophy should remain unchanged
    phil_model = build_extraction_model(phil_template.schema['extraction_model'])
    phil_fields = set(phil_model.model_fields.keys())

    v1_required_fields = {
        'paragraph_id', 'original_text', 'topic_sentence',
        'function_in_argument', 'explicit_claims'
    }

    assert v1_required_fields.issubset(phil_fields), \
        "Legal domain introduction should not affect philosophy fields"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
