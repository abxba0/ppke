"""Template discovery and loading system."""

from pathlib import Path
from typing import Dict

import yaml

from ppke.templates.base import PluginTemplate


# Template directories
OFFICIAL_TEMPLATES_DIR = Path(__file__).parent / "official"
CUSTOM_TEMPLATES_DIR = Path.home() / ".ppke" / "plugins"


def discover_templates() -> Dict[str, Path]:
    """
    Discover all available templates (Tier 1 Official + Tier 2 Custom).

    Searches for templates in:
    1. ppke/templates/official/ (Tier 1: Official templates)
    2. ~/.ppke/plugins/ (Tier 2: User-created custom templates)

    A valid template directory must contain at least a template.yml file.

    Returns:
        Dictionary mapping template name -> template directory path

    Example:
        >>> templates = discover_templates()
        >>> templates
        {
            'philosophy': PosixPath('/path/to/ppke/templates/official/philosophy'),
            'legal': PosixPath('/path/to/ppke/templates/official/legal'),
            'scientific': PosixPath('/home/user/.ppke/plugins/scientific')
        }

    Note:
        - Official templates take precedence over custom templates with the same name
        - Only directories with template.yml are considered valid templates
    """
    templates = {}

    # Tier 1: Official templates (shipped with PPKE)
    if OFFICIAL_TEMPLATES_DIR.exists():
        for template_dir in OFFICIAL_TEMPLATES_DIR.iterdir():
            if template_dir.is_dir() and (template_dir / "template.yml").exists():
                templates[template_dir.name] = template_dir

    # Tier 2: Custom user templates
    if CUSTOM_TEMPLATES_DIR.exists():
        for template_dir in CUSTOM_TEMPLATES_DIR.iterdir():
            if template_dir.is_dir() and (template_dir / "template.yml").exists():
                # Official templates take precedence
                if template_dir.name not in templates:
                    templates[template_dir.name] = template_dir

    return templates


def load_template(domain: str) -> PluginTemplate:
    """
    Load and validate a template by domain name.

    This function:
    1. Discovers available templates
    2. Loads template.yml, prompts.yml, schema.yml, outputs.yml
    3. Validates the template structure
    4. Returns a validated PluginTemplate instance

    Args:
        domain: Template name (e.g., 'philosophy', 'legal', 'scientific')

    Returns:
        Validated PluginTemplate instance

    Raises:
        ValueError: If domain not found or validation fails
        FileNotFoundError: If required template files are missing
        yaml.YAMLError: If YAML files are malformed

    Example:
        >>> template = load_template('philosophy')
        >>> template.name
        'philosophy'
        >>> template.stages
        [{'id': 'extraction', 'name': 'Structural Extraction', ...}, ...]

    Usage:
        ```python
        from ppke.templates.loader import load_template

        # Load philosophy template
        template = load_template('philosophy')

        # Use in pipeline
        for stage in template.stages:
            print(f"Running {stage['name']}...")
        ```
    """
    templates = discover_templates()

    if domain not in templates:
        available = ', '.join(sorted(templates.keys()))
        raise ValueError(
            f"Unknown domain '{domain}'. Available domains: {available}\n"
            f"Searched in:\n"
            f"  - Official: {OFFICIAL_TEMPLATES_DIR}\n"
            f"  - Custom: {CUSTOM_TEMPLATES_DIR}"
        )

    template_path = templates[domain]

    # Load template configuration (required)
    config_file = template_path / "template.yml"
    if not config_file.exists():
        raise FileNotFoundError(f"Template '{domain}' missing template.yml at {template_path}")

    with open(config_file, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Load prompts (optional)
    prompts_file = template_path / "prompts.yml"
    if prompts_file.exists():
        with open(prompts_file, encoding='utf-8') as f:
            prompts = yaml.safe_load(f) or {}
    else:
        prompts = {}

    # Load schema (optional, but recommended)
    schema_file = template_path / "schema.yml"
    if schema_file.exists():
        with open(schema_file, encoding='utf-8') as f:
            schema = yaml.safe_load(f) or {}
    else:
        schema = {}

    # Load outputs (optional)
    outputs_file = template_path / "outputs.yml"
    if outputs_file.exists():
        with open(outputs_file, encoding='utf-8') as f:
            outputs = yaml.safe_load(f) or {}
    else:
        outputs = {}

    # Build PluginTemplate
    template = PluginTemplate(
        name=config['name'],
        version=config['version'],
        tier=config.get('tier', 'custom'),  # Default to 'custom' if not specified
        author=config.get('author', 'Unknown'),
        description=config.get('description', ''),
        stages=config.get('stages', []),
        prompts=prompts,
        schema=schema,
        outputs=outputs,
        skip_chapters=config.get('skip_chapters', [])
    )

    # Validate template
    from ppke.templates.validator import validate_template
    validate_template(template)

    return template


def list_templates() -> list[tuple[str, str, str]]:
    """
    List all available templates with metadata.

    Returns:
        List of tuples (name, tier, description)

    Example:
        >>> for name, tier, desc in list_templates():
        ...     print(f"{name} ({tier}): {desc}")
        philosophy (official): Philosophical text analysis with argument mapping
        legal (official): Legal document analysis
        scientific (custom): Scientific paper analysis
    """
    templates_data = []

    for name, _path in discover_templates().items():
        try:
            template = load_template(name)
            templates_data.append((template.name, template.tier, template.description))
        except Exception as e:
            # If template fails to load, include it with error message
            templates_data.append((name, "error", f"Failed to load: {e}"))

    return sorted(templates_data, key=lambda x: (x[1] != 'official', x[0]))


def get_template_path(domain: str) -> Path:
    """
    Get the file system path for a template.

    Args:
        domain: Template name

    Returns:
        Path to template directory

    Raises:
        ValueError: If template not found
    """
    templates = discover_templates()
    if domain not in templates:
        available = ', '.join(sorted(templates.keys()))
        raise ValueError(f"Unknown domain '{domain}'. Available: {available}")

    return templates[domain]
