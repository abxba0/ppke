"""Dynamic prompt loading from templates - REFACTORED for v2.0"""

from ppke.templates.base import PluginTemplate


def load_prompt(template: PluginTemplate, prompt_id: str, format_vars: dict = None) -> tuple[str, str]:
    """
    Load system and user prompts from template.

    This function replaces the hardcoded prompt constants from v1.x with dynamic
    template-based loading. Prompts are now defined in template YAML files.

    Args:
        template: Loaded PluginTemplate instance
        prompt_id: Prompt identifier (e.g., 'extraction', 'logical_map', 'concepts')
        format_vars: Optional variables to format user_template (e.g., {'chapter_number': 1, 'book_title': 'Meditations'})

    Returns:
        (system_prompt, user_prompt) tuple

    Raises:
        ValueError: If prompt_id not found in template

    Example:
        >>> from ppke.templates import load_template
        >>> template = load_template('philosophy')
        >>> system, user = load_prompt(template, 'extraction', {
        ...     'book_title': 'Meditations',
        ...     'author': 'Marcus Aurelius',
        ...     'chapter_num': 1,
        ...     'chapter_title': 'Book I',
        ...     'paragraphs_json': '[...]'
        ... })
        >>> print(system[:50])
        'Structural extractor for philosophical texts...'

    Usage in pipeline:
        ```python
        template = load_template('philosophy')
        system_prompt, user_prompt = load_prompt(
            template,
            'extraction',
            format_vars={'book_title': book.title, ...}
        )

        # Pass to LLM
        response = llm_client.call(system=system_prompt, user=user_prompt)
        ```

    Migration from v1.x:
        **Before** (v1.x):
        ```python
        from ppke.llm.prompts import STRUCTURAL_EXTRACTION_SYSTEM, STRUCTURAL_EXTRACTION_USER
        system = STRUCTURAL_EXTRACTION_SYSTEM
        user = STRUCTURAL_EXTRACTION_USER.format(book_title=book.title, ...)
        ```

        **After** (v2.0):
        ```python
        from ppke.llm.prompts import load_prompt
        from ppke.templates import load_template
        template = load_template('philosophy')
        system, user = load_prompt(template, 'extraction', {'book_title': book.title, ...})
        ```
    """
    if prompt_id not in template.prompts:
        available = ', '.join(sorted(template.prompts.keys()))
        raise ValueError(
            f"Prompt '{prompt_id}' not found in template '{template.name}'. "
            f"Available prompts: {available}"
        )

    prompt_config = template.prompts[prompt_id]

    # Get system prompt
    system_prompt = prompt_config.get('system', '')

    # Get user template
    user_template = prompt_config.get('user_template', '')

    # Format user prompt if variables provided
    if format_vars:
        try:
            user_prompt = user_template.format(**format_vars)
        except KeyError as e:
            raise ValueError(
                f"Missing format variable for prompt '{prompt_id}': {e}. "
                f"Template requires: {_extract_template_vars(user_template)}"
            )
    else:
        user_prompt = user_template

    return system_prompt, user_prompt


def _extract_template_vars(template_str: str) -> list[str]:
    """
    Extract template variable names from format string.

    Args:
        template_str: String with {var} placeholders

    Returns:
        List of variable names

    Example:
        >>> _extract_template_vars("Hello {name}, chapter {num}")
        ['name', 'num']
    """
    import re
    # Find all {variable_name} patterns
    matches = re.findall(r'\{([^}]+)\}', template_str)
    return list(set(matches))


# ============================================================================
# BACKWARD COMPATIBILITY LAYER (v1.x)
# ============================================================================
# These constants are kept for backward compatibility with existing code.
# They will be deprecated in v3.0.
#
# NEW CODE SHOULD USE load_prompt() instead!
# ============================================================================

# Note: These are loaded from the default philosophy template
# They are functionally identical to v1.x hardcoded prompts

def _load_legacy_prompts():
    """Load prompts from philosophy template for backward compatibility."""
    try:
        from ppke.templates import load_template
        template = load_template('philosophy')

        # Extract prompts for backward compatibility
        extraction = template.prompts.get('extraction', {})
        logical_map = template.prompts.get('logical_map', {})
        concepts = template.prompts.get('concepts', {})
        patterns = template.prompts.get('patterns', {})
        author_model = template.prompts.get('author_model', {})
        cross_book = template.prompts.get('cross_book', {})
        single_book_query = template.prompts.get('single_book_query', {})
        concept_dedup = template.prompts.get('concept_dedup', {})

        return {
            'STRUCTURAL_EXTRACTION_SYSTEM': extraction.get('system', ''),
            'STRUCTURAL_EXTRACTION_USER': extraction.get('user_template', ''),
            'LOGICAL_MAP_SYSTEM': logical_map.get('system', ''),
            'LOGICAL_MAP_USER': logical_map.get('user_template', ''),
            'CONCEPT_INDEX_SYSTEM': concepts.get('system', ''),
            'CONCEPT_INDEX_USER': concepts.get('user_template', ''),
            'PATTERN_DETECTION_SYSTEM': patterns.get('system', ''),
            'PATTERN_DETECTION_USER': patterns.get('user_template', ''),
            'AUTHOR_MODEL_SYSTEM': author_model.get('system', ''),
            'AUTHOR_MODEL_USER': author_model.get('user_template', ''),
            'CROSS_BOOK_SYSTEM': cross_book.get('system', ''),
            'CROSS_BOOK_USER': cross_book.get('user_template', ''),
            'SINGLE_BOOK_QUERY_SYSTEM': single_book_query.get('system', ''),
            'SINGLE_BOOK_QUERY_USER': single_book_query.get('user_template', ''),
            'CONCEPT_DEDUP_SYSTEM': concept_dedup.get('system', ''),
            'CONCEPT_DEDUP_USER': concept_dedup.get('user_template', ''),
        }
    except Exception as e:
        # Fallback: Return empty strings if template loading fails
        print(f"⚠️  Warning: Could not load legacy prompts from template: {e}")
        return {
            'STRUCTURAL_EXTRACTION_SYSTEM': '',
            'STRUCTURAL_EXTRACTION_USER': '',
            'LOGICAL_MAP_SYSTEM': '',
            'LOGICAL_MAP_USER': '',
            'CONCEPT_INDEX_SYSTEM': '',
            'CONCEPT_INDEX_USER': '',
            'PATTERN_DETECTION_SYSTEM': '',
            'PATTERN_DETECTION_USER': '',
            'AUTHOR_MODEL_SYSTEM': '',
            'AUTHOR_MODEL_USER': '',
            'CROSS_BOOK_SYSTEM': '',
            'CROSS_BOOK_USER': '',
            'SINGLE_BOOK_QUERY_SYSTEM': '',
            'SINGLE_BOOK_QUERY_USER': '',
            'CONCEPT_DEDUP_SYSTEM': '',
            'CONCEPT_DEDUP_USER': '',
        }


# Load legacy prompts on module import
_LEGACY_PROMPTS = _load_legacy_prompts()

# Export legacy constants (DEPRECATED - use load_prompt() instead)
STRUCTURAL_EXTRACTION_SYSTEM = _LEGACY_PROMPTS['STRUCTURAL_EXTRACTION_SYSTEM']
STRUCTURAL_EXTRACTION_USER = _LEGACY_PROMPTS['STRUCTURAL_EXTRACTION_USER']
LOGICAL_MAP_SYSTEM = _LEGACY_PROMPTS['LOGICAL_MAP_SYSTEM']
LOGICAL_MAP_USER = _LEGACY_PROMPTS['LOGICAL_MAP_USER']
CONCEPT_INDEX_SYSTEM = _LEGACY_PROMPTS['CONCEPT_INDEX_SYSTEM']
CONCEPT_INDEX_USER = _LEGACY_PROMPTS['CONCEPT_INDEX_USER']
PATTERN_DETECTION_SYSTEM = _LEGACY_PROMPTS['PATTERN_DETECTION_SYSTEM']
PATTERN_DETECTION_USER = _LEGACY_PROMPTS['PATTERN_DETECTION_USER']
AUTHOR_MODEL_SYSTEM = _LEGACY_PROMPTS['AUTHOR_MODEL_SYSTEM']
AUTHOR_MODEL_USER = _LEGACY_PROMPTS['AUTHOR_MODEL_USER']
CROSS_BOOK_SYSTEM = _LEGACY_PROMPTS['CROSS_BOOK_SYSTEM']
CROSS_BOOK_USER = _LEGACY_PROMPTS['CROSS_BOOK_USER']
SINGLE_BOOK_QUERY_SYSTEM = _LEGACY_PROMPTS['SINGLE_BOOK_QUERY_SYSTEM']
SINGLE_BOOK_QUERY_USER = _LEGACY_PROMPTS['SINGLE_BOOK_QUERY_USER']
CONCEPT_DEDUP_SYSTEM = _LEGACY_PROMPTS['CONCEPT_DEDUP_SYSTEM']
CONCEPT_DEDUP_USER = _LEGACY_PROMPTS['CONCEPT_DEDUP_USER']
