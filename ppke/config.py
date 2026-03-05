"""Configuration management for PPKE."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".ppke" / "config.json"
DEFAULT_ENV_PATH = Path.home() / ".ppke" / ".env"
DEFAULT_VAULT_PATH = Path.home() / "KnowledgeBase"

# All supported providers and their default models
PROVIDER_DEFAULTS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-1.5-pro",
    "openrouter": "openai/gpt-4o",
}

# Default small/cheap models per provider (used for Skill 1 & 2)
PROVIDER_SMALL_MODEL_DEFAULTS = {
    "anthropic": "claude-3-haiku-20240307",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-1.5-flash",
    "openrouter": "openai/gpt-4o-mini",
}

SUPPORTED_PROVIDERS = list(PROVIDER_DEFAULTS.keys())


def _load_env_file(path: Path | None = None) -> dict[str, str]:
    """Load key=value pairs from a .env file."""
    path = path or DEFAULT_ENV_PATH
    env_vars: dict[str, str] = {}
    if not path.exists():
        return env_vars
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip a matching pair of surrounding quotes (single or double) only.
        # .strip("\"'") is intentionally avoided — it strips any mix of both
        # characters from both ends, which can mangle values like "key'".
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env_vars[key] = value
    return env_vars


def save_env_file(env_vars: dict[str, str], path: Path | None = None) -> None:
    """Merge *env_vars* into the .env file and set permissions to 0o600."""
    path = path or DEFAULT_ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_env_file(path)
    existing.update(env_vars)
    lines = [f"{k}={v}" for k, v in sorted(existing.items()) if v]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def is_first_run() -> bool:
    """Check if this is the first time PPKE is being run."""
    return not DEFAULT_CONFIG_PATH.exists()


# Map provider name -> environment variable name for its API key
PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    small_model: str | None = None  # Cheaper model for Skill 1 (Extraction); defaults per-provider
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    max_tokens: int = 4096
    max_tokens_extraction: int = 4096  # Token budget for extraction stage (Skill 1)
    max_tokens_analysis: int = 4096  # Token budget for analysis stages (Skills 3-5)
    max_tokens_author: int = 3072  # Token budget for author model (Skill 7) — typically shorter
    temperature: float = 0.2
    paragraphs_per_batch: int = 5
    max_paragraph_tokens: int = 2000  # Split paragraphs exceeding this
    max_workers: int = 4  # Parallel extraction workers

    def __post_init__(self):
        # Load from .env file first, then fall back to environment
        dot_env = _load_env_file()
        if self.anthropic_api_key is None:
            self.anthropic_api_key = (
                os.environ.get("ANTHROPIC_API_KEY")
                or dot_env.get("ANTHROPIC_API_KEY")
            )
        if self.openai_api_key is None:
            self.openai_api_key = (
                os.environ.get("OPENAI_API_KEY")
                or dot_env.get("OPENAI_API_KEY")
            )
        if self.deepseek_api_key is None:
            self.deepseek_api_key = (
                os.environ.get("DEEPSEEK_API_KEY")
                or dot_env.get("DEEPSEEK_API_KEY")
            )
        if self.gemini_api_key is None:
            self.gemini_api_key = (
                os.environ.get("GEMINI_API_KEY")
                or dot_env.get("GEMINI_API_KEY")
            )
        if self.openrouter_api_key is None:
            self.openrouter_api_key = (
                os.environ.get("OPENROUTER_API_KEY")
                or dot_env.get("OPENROUTER_API_KEY")
            )

    @property
    def active_api_key(self) -> str | None:
        """Return the API key for the currently active provider."""
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "gemini": self.gemini_api_key,
            "openrouter": self.openrouter_api_key,
        }.get(self.provider)

    @property
    def effective_small_model(self) -> str:
        """Return the small model to use, falling back to the provider default."""
        if self.small_model:
            return self.small_model
        return PROVIDER_SMALL_MODEL_DEFAULTS.get(self.provider, self.model)


PROCESSING_MODES = ("linear", "swarm")


@dataclass
class Config:
    """Global PPKE configuration."""

    vault_path: Path = field(default_factory=lambda: DEFAULT_VAULT_PATH)
    llm: LLMConfig = field(default_factory=LLMConfig)
    selective_depth: bool = True
    double_pass: bool = False
    default_domain: str = "philosophy"
    enable_vector_search: bool = True
    enable_knowledge_graph: bool = True
    async_ingest: bool = False
    processing_mode: str = "linear"

    def save(self, path: Path | None = None) -> None:
        """Serialize configuration to JSON and write to *path*."""
        path = path or DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "vault_path": str(self.vault_path),
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "small_model": self.llm.small_model,
                "max_tokens": self.llm.max_tokens,
                "max_tokens_extraction": self.llm.max_tokens_extraction,
                "max_tokens_analysis": self.llm.max_tokens_analysis,
                "max_tokens_author": self.llm.max_tokens_author,
                "temperature": self.llm.temperature,
                "paragraphs_per_batch": self.llm.paragraphs_per_batch,
                "max_paragraph_tokens": self.llm.max_paragraph_tokens,
                "max_workers": self.llm.max_workers,
            },
            "selective_depth": self.selective_depth,
            "double_pass": self.double_pass,
            "default_domain": self.default_domain,
            "enable_vector_search": self.enable_vector_search,
            "enable_knowledge_graph": self.enable_knowledge_graph,
            "async_ingest": self.async_ingest,
            "processing_mode": self.processing_mode,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Load configuration from *path*, returning defaults if not found."""
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
                small_model=llm_data.get("small_model", None),
                max_tokens=llm_data.get("max_tokens", 4096),
                max_tokens_extraction=llm_data.get("max_tokens_extraction", 4096),
                max_tokens_analysis=llm_data.get("max_tokens_analysis", 4096),
                max_tokens_author=llm_data.get("max_tokens_author", 3072),
                temperature=llm_data.get("temperature", 0.2),
                paragraphs_per_batch=llm_data.get("paragraphs_per_batch", 5),
                max_paragraph_tokens=llm_data.get("max_paragraph_tokens", 2000),
                max_workers=llm_data.get("max_workers", 4),
            ),
            selective_depth=data.get("selective_depth", True),
            double_pass=data.get("double_pass", False),
            default_domain=data.get("default_domain", "philosophy"),
            enable_vector_search=data.get("enable_vector_search", True),
            enable_knowledge_graph=data.get("enable_knowledge_graph", True),
            async_ingest=data.get("async_ingest", False),
            processing_mode=data.get("processing_mode", "linear"),
        )
