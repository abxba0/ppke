"""Stage alias: concept / entity indexing.

Templates may reference this module as ``ppke.pipeline.stages.concepts``.
The actual implementation lives in ``ppke.pipeline.concepts``.
"""
from ppke.pipeline.concepts import build_concept_index  # re-exported for template discovery

__all__ = ["build_concept_index"]
