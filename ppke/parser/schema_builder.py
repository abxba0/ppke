"""Dynamic Pydantic model generation from template schemas."""

from typing import Any, Optional, Type

from pydantic import BaseModel, Field, create_model

from ppke.parser.models import BaseExtraction


def build_extraction_model(template_schema: dict[str, Any]) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic model from template schema.

    Args:
        template_schema: Template's schema.yml content (parsed YAML)
            Expected structure:
            {
                'name': 'PhilosophyExtraction',
                'base': 'BaseExtraction',
                'description': '...',
                'fields': [
                    {'name': 'function_in_argument', 'type': 'str', 'description': '...'},
                    {'name': 'explicit_claims', 'type': 'list[str]', 'default': []},
                    ...
                ]
            }

    Returns:
        Pydantic model class with template-defined fields

    Example:
        Philosophy schema:
        {
            'name': 'PhilosophyExtraction',
            'base': 'BaseExtraction',
            'fields': [
                {'name': 'function_in_argument', 'type': 'str', 'description': '...'},
                {'name': 'explicit_claims', 'type': 'list[str]', 'default': []},
            ]
        }

        Legal schema:
        {
            'name': 'LegalExtraction',
            'base': 'BaseExtraction',
            'fields': [
                {'name': 'legal_standard', 'type': 'str', 'description': '...'},
                {'name': 'case_references', 'type': 'list[str]', 'default': []},
            ]
        }

    Usage:
        >>> schema = {'name': 'TestExtraction', 'base': 'BaseExtraction', 'fields': [...]}
        >>> TestExtraction = build_extraction_model(schema)
        >>> result = TestExtraction(paragraph_id='test', original_text='...', custom_field='value')
    """
    # Extract model name
    model_name = template_schema.get('name', 'DynamicExtraction')

    # Determine base model
    base_class_name = template_schema.get('base', 'BaseExtraction')

    # Currently only support BaseExtraction as base
    # Future: Could support custom bases
    if base_class_name == 'BaseExtraction':
        base_class = BaseExtraction
    else:
        raise ValueError(f"Unsupported base class: {base_class_name}. Only 'BaseExtraction' is supported.")

    # Build field definitions
    fields = {}
    for field_def in template_schema.get('fields', []):
        field_name = field_def['name']

        # Parse type string (e.g., "str", "list[str]", "int", "Optional[str]")
        field_type = _parse_type(field_def['type'])

        # Get description and default
        field_desc = field_def.get('description', '')

        # Check if default is specified
        if 'default' in field_def:
            field_default = field_def['default']
            fields[field_name] = (field_type, Field(default=field_default, description=field_desc))
        else:
            # Required field (use ... as sentinel)
            fields[field_name] = (field_type, Field(description=field_desc))

    # Create dynamic model
    dynamic_model = create_model(
        model_name,
        __base__=base_class,
        **fields
    )

    return dynamic_model


def _parse_type(type_str: str) -> Type:
    """
    Parse type string to Python type.

    Examples:
        'str' -> str
        'int' -> int
        'list[str]' -> list[str]
        'Optional[str]' -> Optional[str]
        'dict' -> dict
        'bool' -> bool
        'float' -> float

    Args:
        type_str: Type as string

    Returns:
        Python type object

    Raises:
        ValueError: If type string is not supported
    """
    # Remove whitespace
    type_str = type_str.strip()

    # Simple types
    simple_types = {
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        'dict': dict,
        'list': list,
        'any': Any,
    }

    if type_str.lower() in simple_types:
        return simple_types[type_str.lower()]

    # List types: list[<inner_type>]
    if type_str.startswith('list[') and type_str.endswith(']'):
        inner_type_str = type_str[5:-1].strip()
        inner_type = _parse_type(inner_type_str)
        return list[inner_type]

    # Dict types: dict[<key_type>, <value_type>]
    if type_str.startswith('dict[') and type_str.endswith(']'):
        inner = type_str[5:-1].strip()
        # Simple dict (no type params)
        if not inner:
            return dict
        # dict[str, Any] or similar
        parts = inner.split(',')
        if len(parts) == 2:
            key_type = _parse_type(parts[0].strip())
            val_type = _parse_type(parts[1].strip())
            return dict[key_type, val_type]
        return dict

    # Optional types: Optional[<inner_type>]
    if type_str.startswith('Optional[') and type_str.endswith(']'):
        inner_type_str = type_str[9:-1].strip()
        inner_type = _parse_type(inner_type_str)
        return Optional[inner_type]

    # If none of the above, raise error
    raise ValueError(
        f"Unsupported type string: '{type_str}'. "
        f"Supported: str, int, float, bool, dict, list, list[T], Optional[T], dict[K,V]"
    )


def validate_schema(schema: dict[str, Any]) -> None:
    """
    Validate that a schema definition is well-formed.

    Args:
        schema: Schema dictionary to validate

    Raises:
        ValueError: If schema is invalid
    """
    # Check required top-level keys
    if 'name' not in schema:
        raise ValueError("Schema missing required field: 'name'")

    if 'fields' not in schema:
        raise ValueError("Schema missing required field: 'fields'")

    # Validate fields
    if not isinstance(schema['fields'], list):
        raise ValueError("Schema 'fields' must be a list")

    for i, field_def in enumerate(schema['fields']):
        if not isinstance(field_def, dict):
            raise ValueError(f"Field {i} is not a dictionary")

        if 'name' not in field_def:
            raise ValueError(f"Field {i} missing 'name'")

        if 'type' not in field_def:
            raise ValueError(f"Field {i} ({field_def.get('name', '?')}) missing 'type'")

        # Try to parse the type
        try:
            _parse_type(field_def['type'])
        except ValueError as e:
            raise ValueError(
                f"Field {i} ({field_def.get('name', '?')}) has invalid type: {e}"
            ) from e
