"""Configuration management for PPKE."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = Path.home() / ".ppke" / "config.json"
DEFAULT_VAULT_PATH = Path.home() / "KnowledgeBase"


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "anthropic"  # "anthropic" or "openai"
    model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.2
    paragraphs_per_batch: int = 5

    def __post_init__(self):
        if self.anthropic_api_key is None:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if self.openai_api_key is None:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY")

    @property
    def active_api_key(self) -> Optional[str]:
        if self.provider == "anthropic":
            return self.anthropic_api_key
        return self.openai_api_key


@dataclass
class Config:
    """Global PPKE configuration."""

    vault_path: Path = field(default_factory=lambda: DEFAULT_VAULT_PATH)
    llm: LLMConfig = field(default_factory=LLMConfig)
    selective_depth: bool = True
    double_pass: bool = False

    def save(self, path: Optional[Path] = None):
        path = path or DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "vault_path": str(self.vault_path),
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
                "paragraphs_per_batch": self.llm.paragraphs_per_batch,
            },
            "selective_depth": self.selective_depth,
            "double_pass": self.double_pass,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Config:
        path = path or DEFAULT_CONFIG_PATH
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        llm_data = data.get("llm", {})
        return cls(
            vault_path=Path(data.get("vault_path", str(DEFAULT_VAULT_PATH))),
            llm=LLMConfig(
                provider=llm_data.get("provider", "anthropic"),
                model=llm_data.get("model", "claude-sonnet-4-20250514"),
                max_tokens=llm_data.get("max_tokens", 4096),
                temperature=llm_data.get("temperature", 0.2),
                paragraphs_per_batch=llm_data.get("paragraphs_per_batch", 5),
            ),
            selective_depth=data.get("selective_depth", True),
            double_pass=data.get("double_pass", False),
        )
