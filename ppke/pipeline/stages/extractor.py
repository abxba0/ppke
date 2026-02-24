"""Stage alias: structural extraction.

Templates may reference this module as ``ppke.pipeline.stages.extractor``.
The actual implementation lives in ``ppke.pipeline.extractor``.
"""
from ppke.pipeline.extractor import extract_chapter  # re-exported for template discovery

__all__ = ["extract_chapter"]
