"""Stage alias: pattern / findings detection.

Templates may reference this module as ``ppke.pipeline.stages.patterns``.
The actual implementation lives in ``ppke.pipeline.patterns``.
"""
from ppke.pipeline.patterns import detect_patterns  # re-exported for template discovery

__all__ = ["detect_patterns"]
