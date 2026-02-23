"""Base classes for PPKE plugin templates."""

from pydantic import BaseModel, Field
from typing import Any


class PluginTemplate(BaseModel):
    """
    Base class for domain templates.

    A PluginTemplate defines how PPKE should process documents in a specific domain
    (e.g., philosophy, legal, scientific). It specifies the extraction schema,
    prompts, pipeline stages, and output formats.

    Attributes:
        name: Template identifier (e.g., 'philosophy', 'legal', 'scientific')
        version: Semantic version (e.g., '2.0.0')
        tier: 'official' (Tier 1, shipped with PPKE) or 'custom' (Tier 2, user-created)
        author: Creator name
        description: Brief description of what this template analyzes
        stages: List of pipeline stages to execute (order matters)
        prompts: Prompt templates (loaded from prompts.yml)
        schema: Pydantic schema definition (loaded from schema.yml)
        outputs: Output file templates (loaded from outputs.yml)
        skip_chapters: Chapter titles to skip during ingestion (e.g., ['bibliography', 'index'])

    Example template.yml:
        ```yaml
        name: philosophy
        version: "2.0.0"
        tier: official
        author: PPKE Core Team
        description: "Philosophical text analysis with argument mapping"

        stages:
          - id: extraction
            name: "Structural Extraction"
            module: ppke.pipeline.stages.extractor
            prompt: extraction

          - id: logical_map
            name: "Logical Architecture"
            module: ppke.pipeline.stages.analyzer
            prompt: logical_map
            output_file: "02_Logical_Map.md"

        skip_chapters:
          - bibliography
          - index
          - appendix
        ```

    Security:
        - Templates are validated before loading
        - No arbitrary code execution allowed
        - Only YAML configuration files are processed
    """

    name: str = Field(..., min_length=1, pattern=r'^[a-z_]+$', description="Template identifier (lowercase, underscore-separated)")
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$', description="Semantic version")
    tier: str = Field(..., pattern=r'^(official|custom)$', description="Template tier: 'official' or 'custom'")
    author: str = Field(..., description="Creator name")
    description: str = Field(..., description="Brief description of template purpose")

    stages: list[dict[str, Any]] = Field(default_factory=list, description="Pipeline stages to execute")
    prompts: dict[str, Any] = Field(default_factory=dict, description="Prompt templates")
    schema: dict[str, Any] = Field(default_factory=dict, description="Extraction schema definition")
    outputs: dict[str, Any] = Field(default_factory=dict, description="Output file templates")
    skip_chapters: list[str] = Field(default_factory=list, description="Chapter titles to skip (lowercase)")

    model_config = {
        "extra": "forbid",  # Prevent accidental fields
        "validate_assignment": True,
        "str_strip_whitespace": True
    }

    def get_stage_by_id(self, stage_id: str) -> dict[str, Any] | None:
        """
        Get a stage configuration by its ID.

        Args:
            stage_id: Stage identifier (e.g., 'extraction', 'logical_map')

        Returns:
            Stage configuration dict or None if not found
        """
        for stage in self.stages:
            if stage.get('id') == stage_id:
                return stage
        return None

    def get_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        """
        Get a prompt configuration by its ID.

        Args:
            prompt_id: Prompt identifier (e.g., 'extraction', 'logical_map')

        Returns:
            Prompt configuration dict or None if not found
        """
        return self.prompts.get(prompt_id)

    def should_skip_chapter(self, chapter_title: str) -> bool:
        """
        Check if a chapter should be skipped based on its title.

        Args:
            chapter_title: Chapter title (case-insensitive)

        Returns:
            True if chapter should be skipped
        """
        normalized_title = chapter_title.lower().strip()
        return any(skip_title.lower() in normalized_title for skip_title in self.skip_chapters)
