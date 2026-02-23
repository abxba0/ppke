"""PPKE Template System - Domain-agnostic knowledge processing framework."""

from ppke.templates.base import PluginTemplate
from ppke.templates.loader import load_template, discover_templates, list_templates
from ppke.templates.validator import validate_template

__all__ = [
    'PluginTemplate',
    'load_template',
    'discover_templates',
    'list_templates',
    'validate_template',
]
