"""Template validation and security checks."""

import re

from ppke.templates.base import PluginTemplate


def validate_template(template: PluginTemplate) -> None:
    """
    Validate template structure and security.

    This function performs:
    1. Required fields validation
    2. Stage configuration validation
    3. Schema validation
    4. Security checks (prevent code injection)
    5. Sanity checks (e.g., prompt length warnings)

    Args:
        template: PluginTemplate instance to validate

    Raises:
        ValueError: If validation fails

    Example:
        >>> from ppke.templates.loader import load_template
        >>> template = load_template('philosophy')
        >>> validate_template(template)  # Raises ValueError if invalid
    """
    # Validate required fields
    _validate_required_fields(template)

    # Validate stages
    _validate_stages(template)

    # Validate schema
    _validate_schema(template)

    # Security checks
    _security_check(template)

    # Warnings (non-fatal)
    _check_warnings(template)


def _validate_required_fields(template: PluginTemplate) -> None:
    """Validate that required fields are present."""
    if not template.stages:
        raise ValueError(f"Template '{template.name}' has no stages defined in template.yml")

    if not template.schema:
        raise ValueError(f"Template '{template.name}' has no schema defined in schema.yml")

    if not template.prompts:
        raise ValueError(f"Template '{template.name}' has no prompts defined in prompts.yml")


def _validate_stages(template: PluginTemplate) -> None:
    """Validate stage configurations."""
    required_stage_keys = ['id', 'name', 'module']

    for i, stage in enumerate(template.stages):
        # Check required keys
        for key in required_stage_keys:
            if key not in stage:
                raise ValueError(
                    f"Template '{template.name}': Stage {i} missing required key '{key}'. "
                    f"Stage config: {stage}"
                )

        # Validate stage ID format
        stage_id = stage['id']
        if not re.match(r'^[a-z_]+$', stage_id):
            raise ValueError(
                f"Template '{template.name}': Stage ID '{stage_id}' must be lowercase with underscores only"
            )

        # Validate module path
        module = stage['module']
        if not re.match(r'^[a-z_.]+$', module):
            raise ValueError(
                f"Template '{template.name}': Stage module '{module}' contains invalid characters"
            )

        # Check that prompt exists if referenced
        if 'prompt' in stage:
            prompt_id = stage['prompt']
            if prompt_id not in template.prompts:
                available_prompts = ', '.join(template.prompts.keys())
                raise ValueError(
                    f"Template '{template.name}': Stage '{stage_id}' references unknown prompt '{prompt_id}'. "
                    f"Available prompts: {available_prompts}"
                )


def _validate_schema(template: PluginTemplate) -> None:
    """Validate schema definition."""
    # Check for extraction_model in schema
    if 'extraction_model' not in template.schema:
        raise ValueError(
            f"Template '{template.name}': schema.yml missing 'extraction_model' definition"
        )

    schema = template.schema['extraction_model']

    # Required schema keys
    if 'name' not in schema:
        raise ValueError(
            f"Template '{template.name}': Schema missing 'extraction_model.name'"
        )

    if 'fields' not in schema:
        raise ValueError(
            f"Template '{template.name}': Schema missing 'extraction_model.fields'"
        )

    # Validate fields
    if not isinstance(schema['fields'], list):
        raise ValueError(
            f"Template '{template.name}': Schema 'extraction_model.fields' must be a list"
        )

    for i, field in enumerate(schema['fields']):
        if not isinstance(field, dict):
            raise ValueError(
                f"Template '{template.name}': Schema field {i} is not a dictionary"
            )

        if 'name' not in field:
            raise ValueError(
                f"Template '{template.name}': Schema field {i} missing 'name'"
            )

        if 'type' not in field:
            raise ValueError(
                f"Template '{template.name}': Schema field {i} ({field.get('name', '?')}) missing 'type'"
            )

        # Validate field name format (should be valid Python identifier)
        field_name = field['name']
        if not re.match(r'^[a-z_][a-z0-9_]*$', field_name):
            raise ValueError(
                f"Template '{template.name}': Schema field name '{field_name}' is not a valid Python identifier. "
                f"Use lowercase with underscores."
            )


def _security_check(template: PluginTemplate) -> None:
    """
    Security validation to prevent code injection.

    Checks for:
    - Suspicious import statements in prompts/config
    - Shell command patterns
    - Eval/exec patterns
    """
    # Convert all template data to string for security scanning
    prompts_str = str(template.prompts)
    config_str = str(template.model_dump())

    # Comprehensive injection detection — covers classic and obfuscated Python attacks
    dangerous_patterns = [
        # Direct imports of dangerous stdlib modules
        (r'import\s+(os|subprocess|sys|shutil|pathlib|socket|importlib|ctypes|pickle|marshal)',
         'dangerous stdlib import'),
        # Dynamic import mechanisms
        (r'__import__\s*\(', '__import__() call'),
        (r'importlib\s*\.\s*import_module', 'importlib.import_module() call'),
        # Code execution sinks
        (r'eval\s*\(', 'eval() call'),
        (r'exec\s*\(', 'exec() call'),
        (r'compile\s*\(', 'compile() call'),
        # OS command execution
        (r'os\s*\.\s*system\s*\(', 'os.system() call'),
        (r'os\s*\.\s*popen\s*\(', 'os.popen() call'),
        (r'os\s*\.\s*spawn', 'os.spawn*() call'),
        (r'subprocess\s*\.', 'subprocess module usage'),
        # Reflection / introspection used for bypassing restrictions
        (r'__builtins__', '__builtins__ access'),
        (r'builtins\s*\.', 'builtins module access'),
        (r'globals\s*\(\s*\)', 'globals() call'),
        (r'locals\s*\(\s*\)', 'locals() call'),
        (r'vars\s*\(\s*\)', 'vars() call'),
        (r'getattr\s*\(', 'getattr() — may bypass attribute access controls'),
        # Shell injection
        (r'\$\{[^}]*\}', 'Shell variable expansion ${...}'),
        (r'`[^`]+`', 'Backtick command execution'),
        (r'\|\s*(bash|sh|zsh|cmd|powershell)', 'Shell pipe to interpreter'),
    ]

    for pattern, description in dangerous_patterns:
        if re.search(pattern, prompts_str, re.IGNORECASE):
            raise ValueError(
                f"Template '{template.name}' SECURITY VIOLATION: "
                f"Prompts contain suspicious pattern: {description}\n"
                f"Templates must not contain executable code."
            )

        if re.search(pattern, config_str, re.IGNORECASE):
            raise ValueError(
                f"Template '{template.name}' SECURITY VIOLATION: "
                f"Configuration contains suspicious pattern: {description}\n"
                f"Templates must not contain executable code."
            )


def _check_warnings(template: PluginTemplate) -> None:
    """Non-fatal warnings for template quality."""
    # Warning: Very long prompts
    for prompt_id, prompt_content in template.prompts.items():
        if isinstance(prompt_content, dict):
            system_prompt = prompt_content.get('system', '')
            if len(system_prompt) > 5000:
                print(
                    f"⚠️  Warning: Template '{template.name}' prompt '{prompt_id}' is very long "
                    f"({len(system_prompt)} chars). Consider splitting into multiple prompts."
                )

            user_template = prompt_content.get('user_template', '')
            if len(user_template) > 3000:
                print(
                    f"⚠️  Warning: Template '{template.name}' prompt '{prompt_id}' user_template is very long "
                    f"({len(user_template)} chars)."
                )

    # Warning: Too many stages (may be slow)
    if len(template.stages) > 10:
        print(
            f"⚠️  Warning: Template '{template.name}' has {len(template.stages)} stages. "
            f"This may result in slow processing and high LLM costs."
        )

    # Warning: Missing description
    if not template.description or len(template.description) < 10:
        print(
            f"⚠️  Warning: Template '{template.name}' has a very short or missing description. "
            f"Please add a meaningful description in template.yml."
        )
