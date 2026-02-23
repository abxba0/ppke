"""Template installation system for PPKE plugins."""

from pathlib import Path
import shutil
import tempfile
import subprocess
import re
import sys
from typing import Optional
from ppke.templates.loader import load_template, CUSTOM_TEMPLATES_DIR
from ppke.templates.validator import validate_template
from ppke.templates.registry import register_plugin


# Check if we can use emojis (fails on Windows console)
def _can_use_emojis() -> bool:
    """Check if stdout supports Unicode emojis."""
    try:
        sys.stdout.encoding
        # Test if we can encode an emoji
        '\U0001f50d'.encode(sys.stdout.encoding or 'utf-8')
        return True
    except (AttributeError, UnicodeEncodeError):
        return False


_USE_EMOJIS = _can_use_emojis()


def _print(msg: str) -> None:
    """Print with emoji fallback for Windows."""
    if not _USE_EMOJIS:
        # Remove emojis and replace with text equivalents
        msg = msg.replace('📥', '[CLONE]')
        msg = msg.replace('🔍', '[VALIDATE]')
        msg = msg.replace('📦', '[INSTALL]')
        msg = msg.replace('✅', '[OK]')
        msg = msg.replace('⚠️', '[WARNING]')
        msg = msg.replace('🗑️', '[DELETE]')
        msg = msg.replace('🔄', '[UPGRADE]')
    print(msg)


class TemplateInstallError(Exception):
    """Raised when template installation fails."""
    pass


def install_from_github(github_url: str, force: bool = False) -> str:
    """
    Install a template from a GitHub repository.

    Args:
        github_url: GitHub repository URL (e.g., https://github.com/user/ppke-template-legal)
        force: If True, overwrite existing template with the same name

    Returns:
        Name of the installed template

    Raises:
        TemplateInstallError: If installation fails

    Example:
        >>> name = install_from_github('https://github.com/user/ppke-template-legal')
        >>> print(f"Installed template: {name}")
        Installed template: legal
    """
    # Validate GitHub URL
    github_pattern = r'https?://github\.com/[\w-]+/[\w-]+'
    if not re.match(github_pattern, github_url):
        raise TemplateInstallError(
            f"Invalid GitHub URL: {github_url}\n"
            f"Expected format: https://github.com/username/repo-name"
        )

    # Check if git is available
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise TemplateInstallError(
            "Git is not installed or not in PATH.\n"
            "Please install git: https://git-scm.com/downloads"
        )

    # Clone to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        _print(f"📥 Cloning from {github_url}...")
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', github_url, str(temp_path / 'repo')],
                capture_output=True,
                check=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise TemplateInstallError(
                f"Failed to clone repository:\n{e.stderr}"
            )

        repo_path = temp_path / 'repo'

        # Install from the cloned directory
        return install_from_local(repo_path, force=force, source=f"github:{github_url}")


def install_from_local(local_path: Path | str, force: bool = False, source: Optional[str] = None) -> str:
    """
    Install a template from a local directory.

    This function:
    1. Validates the template structure
    2. Copies template files to ~/.ppke/plugins/<template_name>
    3. Registers the template in the plugin registry

    Args:
        local_path: Path to template directory
        force: If True, overwrite existing template with the same name
        source: Installation source description (for registry metadata)

    Returns:
        Name of the installed template

    Raises:
        TemplateInstallError: If installation fails

    Example:
        >>> name = install_from_local('./my-custom-template/')
        >>> print(f"Installed template: {name}")
        Installed template: my_domain
    """
    local_path = Path(local_path).resolve()

    if not local_path.exists():
        raise TemplateInstallError(f"Path does not exist: {local_path}")

    if not local_path.is_dir():
        raise TemplateInstallError(f"Path is not a directory: {local_path}")

    # Check for required files
    template_yml = local_path / "template.yml"
    if not template_yml.exists():
        raise TemplateInstallError(
            f"Invalid template: missing template.yml\n"
            f"Template directory must contain at least template.yml"
        )

    # Load and validate template (this will raise errors if invalid)
    _print("🔍 Validating template structure...")

    # Temporarily copy to custom dir to load it
    import yaml
    with open(template_yml, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    template_name = config.get('name')
    if not template_name:
        raise TemplateInstallError("Template missing 'name' field in template.yml")

    # Check if template already exists
    target_path = CUSTOM_TEMPLATES_DIR / template_name
    if target_path.exists() and not force:
        raise TemplateInstallError(
            f"Template '{template_name}' already exists at {target_path}\n"
            f"Use --force to overwrite"
        )

    # Create custom templates directory if it doesn't exist
    CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    # Copy template files
    _print(f"📦 Installing template '{template_name}' to {target_path}...")

    if target_path.exists():
        shutil.rmtree(target_path)

    shutil.copytree(local_path, target_path)

    # Now validate the installed template
    try:
        template = load_template(template_name)
        _print(f"✅ Template '{template_name}' validated successfully")
    except Exception as e:
        # Clean up if validation fails
        if target_path.exists():
            shutil.rmtree(target_path)
        raise TemplateInstallError(f"Template validation failed: {e}")

    # Register in plugin registry
    register_plugin(
        name=template.name,
        tier='custom',
        version=template.version,
        source=source or 'local',
        author=template.author,
        description=template.description
    )

    _print(f"✅ Successfully installed template: {template_name}")
    _print(f"\nUsage:")
    _print(f"  ppke ingest --domain {template_name} document.md")

    return template_name


def uninstall_template(template_name: str, force: bool = False) -> bool:
    """
    Uninstall a custom template.

    This function:
    1. Removes the template directory from ~/.ppke/plugins/
    2. Unregisters the template from the plugin registry

    Note: Official templates cannot be uninstalled.

    Args:
        template_name: Name of the template to uninstall
        force: If True, skip confirmation prompt

    Returns:
        True if template was uninstalled, False if cancelled

    Raises:
        TemplateInstallError: If template is official or not found

    Example:
        >>> uninstall_template('my_domain')
        True
    """
    from ppke.templates.registry import get_plugin_info, unregister_plugin

    # Check if template exists
    plugin_info = get_plugin_info(template_name)
    if not plugin_info:
        raise TemplateInstallError(f"Template '{template_name}' not found")

    # Don't allow uninstalling official templates
    if plugin_info['tier'] == 'official':
        raise TemplateInstallError(
            f"Cannot uninstall official template '{template_name}'\n"
            f"Official templates are bundled with PPKE"
        )

    template_path = CUSTOM_TEMPLATES_DIR / template_name
    if not template_path.exists():
        _print(f"⚠️  Warning: Template directory not found: {template_path}")
        _print(f"Removing from registry anyway...")

    # Confirm uninstallation
    if not force:
        response = input(f"⚠️  Uninstall template '{template_name}'? [y/N]: ")
        if response.lower() != 'y':
            _print("❌ Cancelled")
            return False

    # Remove template directory
    if template_path.exists():
        shutil.rmtree(template_path)
        _print(f"🗑️  Removed template directory: {template_path}")

    # Unregister from registry
    unregister_plugin(template_name)
    _print(f"✅ Uninstalled template: {template_name}")

    return True


def upgrade_template(template_name: str) -> bool:
    """
    Upgrade an installed template to the latest version.

    For GitHub-installed templates, this re-clones from the original URL.
    For locally-installed templates, manual upgrade is required.

    Args:
        template_name: Name of the template to upgrade

    Returns:
        True if upgrade successful

    Raises:
        TemplateInstallError: If template not found or upgrade fails

    Example:
        >>> upgrade_template('legal')
        True
    """
    from ppke.templates.registry import get_plugin_info

    # Get plugin info
    plugin_info = get_plugin_info(template_name)
    if not plugin_info:
        raise TemplateInstallError(f"Template '{template_name}' not found")

    # Check installation source
    source = plugin_info.get('source', '')

    if not source.startswith('github:'):
        raise TemplateInstallError(
            f"Template '{template_name}' was not installed from GitHub\n"
            f"Source: {source}\n"
            f"Manual upgrade required: reinstall with --force"
        )

    # Extract GitHub URL
    github_url = source.replace('github:', '')

    _print(f"🔄 Upgrading '{template_name}' from {github_url}...")

    # Reinstall (force=True to overwrite)
    try:
        install_from_github(github_url, force=True)
        _print(f"✅ Successfully upgraded template: {template_name}")
        return True
    except TemplateInstallError as e:
        raise TemplateInstallError(f"Upgrade failed: {e}")


def list_installed_templates() -> list[dict]:
    """
    List all installed templates with detailed information.

    Returns:
        List of dictionaries with template metadata

    Example:
        >>> templates = list_installed_templates()
        >>> for t in templates:
        ...     print(f"{t['name']} v{t['version']} ({t['tier']})")
        philosophy v2.0.0 (official)
        legal v2.0.0 (official)
        my_domain v1.0.0 (custom)
    """
    from ppke.templates.registry import list_registered_plugins
    return list_registered_plugins()
