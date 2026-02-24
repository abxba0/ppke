"""Stage alias: secondary analysis (logical map / methodology).

Templates may reference this module as ``ppke.pipeline.stages.analyzer``.
The actual implementation lives in ``ppke.pipeline.logical_map``.
"""
from ppke.pipeline.logical_map import build_logical_map  # re-exported for template discovery

__all__ = ["build_logical_map"]
