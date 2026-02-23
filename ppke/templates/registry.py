"""Plugin registry for tracking installed templates."""

from pathlib import Path
import json
from datetime import datetime
from typing import Optional, Dict, Any


REGISTRY_FILE = Path.home() / ".ppke" / "plugin_registry.json"


def get_registry() -> Dict[str, Any]:
    """
    Load plugin registry.

    Returns:
        Registry dictionary with 'plugins' and 'last_updated' keys

    Example:
        >>> registry = get_registry()
        >>> registry
        {
            'plugins': {
                'philosophy': {
                    'name': 'philosophy',
                    'tier': 'official',
                    'version': '2.0.0',
                    ...
                }
            },
            'last_updated': '2026-02-22T12:00:00'
        }
    """
    if not REGISTRY_FILE.exists():
        return {'plugins': {}, 'last_updated': None}

    try:
        with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Warning: Could not load registry: {e}")
        return {'plugins': {}, 'last_updated': None}


def register_plugin(
    name: str,
    tier: str,
    version: str,
    source: str,
    author: Optional[str] = None,
    description: Optional[str] = None
) -> None:
    """
    Register a plugin in the local registry.

    Args:
        name: Plugin name (e.g., 'philosophy', 'legal')
        tier: 'official' or 'custom'
        version: Semantic version (e.g., '2.0.0')
        source: Installation source ('bundled', 'manual', 'github:<url>', 'promoted', etc.)
        author: Plugin author (optional)
        description: Brief description (optional)

    Example:
        >>> register_plugin('philosophy', 'official', '2.0.0', 'bundled', 'PPKE Core Team')
        >>> register_plugin('my_domain', 'custom', '1.0.0', 'manual', 'John Doe')
    """
    registry = get_registry()

    registry['plugins'][name] = {
        'name': name,
        'tier': tier,
        'version': version,
        'source': source,
        'author': author or 'Unknown',
        'description': description or '',
        'installed_at': datetime.utcnow().isoformat()
    }
    registry['last_updated'] = datetime.utcnow().isoformat()

    # Ensure .ppke directory exists
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Save registry
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)


def unregister_plugin(name: str) -> bool:
    """
    Remove plugin from registry.

    Args:
        name: Plugin name to remove

    Returns:
        True if plugin was removed, False if not found

    Example:
        >>> unregister_plugin('my_domain')
        True
    """
    registry = get_registry()

    if name not in registry['plugins']:
        return False

    del registry['plugins'][name]
    registry['last_updated'] = datetime.utcnow().isoformat()

    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)

    return True


def get_plugin_info(name: str) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a registered plugin.

    Args:
        name: Plugin name

    Returns:
        Plugin metadata dictionary or None if not found

    Example:
        >>> info = get_plugin_info('philosophy')
        >>> info['tier']
        'official'
        >>> info['version']
        '2.0.0'
    """
    registry = get_registry()
    return registry['plugins'].get(name)


def list_registered_plugins() -> list[Dict[str, Any]]:
    """
    List all registered plugins.

    Returns:
        List of plugin metadata dictionaries

    Example:
        >>> plugins = list_registered_plugins()
        >>> for plugin in plugins:
        ...     print(f"{plugin['name']} ({plugin['tier']}) - v{plugin['version']}")
        philosophy (official) - v2.0.0
        legal (official) - v2.0.0
        scientific_research (custom) - v1.0.0
    """
    registry = get_registry()
    return list(registry['plugins'].values())


def sync_registry_with_filesystem() -> None:
    """
    Synchronize registry with actual templates on filesystem.

    This function:
    1. Scans ppke/templates/official/ and ~/.ppke/plugins/
    2. Adds any discovered templates not in registry
    3. Removes registry entries for templates that no longer exist

    Should be called periodically to keep registry up-to-date.
    """
    from ppke.templates.loader import discover_templates, load_template

    # Get current registry
    registry = get_registry()
    registered_names = set(registry['plugins'].keys())

    # Discover templates on filesystem
    discovered = discover_templates()
    discovered_names = set(discovered.keys())

    # Add newly discovered templates
    for name in discovered_names - registered_names:
        try:
            template = load_template(name)
            register_plugin(
                name=template.name,
                tier=template.tier,
                version=template.version,
                source='discovered',
                author=template.author,
                description=template.description
            )
            print(f"✅ Registered newly discovered plugin: {name}")
        except Exception as e:
            print(f"⚠️  Could not register {name}: {e}")

    # Remove plugins that no longer exist
    for name in registered_names - discovered_names:
        unregister_plugin(name)
        print(f"🗑️  Unregistered missing plugin: {name}")


def get_registry_stats() -> Dict[str, Any]:
    """
    Get statistics about registered plugins.

    Returns:
        Dictionary with counts and metadata

    Example:
        >>> stats = get_registry_stats()
        >>> stats
        {
            'total': 3,
            'official': 2,
            'custom': 1,
            'last_updated': '2026-02-22T12:00:00'
        }
    """
    registry = get_registry()
    plugins = registry['plugins'].values()

    return {
        'total': len(plugins),
        'official': sum(1 for p in plugins if p['tier'] == 'official'),
        'custom': sum(1 for p in plugins if p['tier'] == 'custom'),
        'last_updated': registry.get('last_updated'),
        'registry_file': str(REGISTRY_FILE)
    }
