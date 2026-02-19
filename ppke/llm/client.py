"""Unified LLM client supporting Anthropic, OpenAI, DeepSeek, Gemini, and OpenRouter."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from ppke.config import LLMConfig

logger = logging.getLogger(__name__)

# Retry settings for rate-limit (429) and transient server errors (5xx)
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2  # 2s, 4s, 8s, 16s

# DeepSeek API base URL (OpenAI-compatible)
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# OpenRouter API base URL (OpenAI-compatible)
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a retryable rate-limit or server error."""
    exc_str = str(exc).lower()
    if "429" in exc_str or "rate" in exc_str:
        return True
    if any(code in exc_str for code in ("500", "502", "503", "529", "overloaded")):
        return True
    cls_name = type(exc).__name__
    if cls_name in ("RateLimitError", "InternalServerError", "OverloadedError"):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (429, 500, 502, 503, 529):
        return True
    return False


class LLMClient:
    """Configurable LLM client wrapping Anthropic, OpenAI, DeepSeek, Gemini, and OpenRouter.

    Thread-safe: lazy client initialization is protected by a lock.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._anthropic_client = None
        self._openai_client = None
        self._deepseek_client = None
        self._gemini_client = None
        self._openrouter_client = None
        self._lock = threading.Lock()

    def _get_anthropic(self) -> Any:
        if self._anthropic_client is None:
            with self._lock:
                if self._anthropic_client is None:
                    import anthropic
                    self._anthropic_client = anthropic.Anthropic(
                        api_key=self.config.anthropic_api_key
                    )
        return self._anthropic_client

    def _get_openai(self) -> Any:
        if self._openai_client is None:
            with self._lock:
                if self._openai_client is None:
                    import openai
                    self._openai_client = openai.OpenAI(
                        api_key=self.config.openai_api_key
                    )
        return self._openai_client

    def _get_deepseek(self) -> Any:
        """Return a lazily-initialized DeepSeek client (OpenAI-compatible)."""
        if self._deepseek_client is None:
            with self._lock:
                if self._deepseek_client is None:
                    import openai
                    self._deepseek_client = openai.OpenAI(
                        api_key=self.config.deepseek_api_key,
                        base_url=_DEEPSEEK_BASE_URL,
                    )
        return self._deepseek_client

    def _get_gemini(self) -> Any:
        """Return a lazily-initialized Gemini generative model."""
        if self._gemini_client is None:
            with self._lock:
                if self._gemini_client is None:
                    import google.generativeai as genai  # type: ignore[import]
                    genai.configure(api_key=self.config.gemini_api_key)
                    self._gemini_client = genai.GenerativeModel(self.config.model)
        return self._gemini_client

    def _get_openrouter(self) -> Any:
        """Return a lazily-initialized OpenRouter client (OpenAI-compatible)."""
        if self._openrouter_client is None:
            with self._lock:
                if self._openrouter_client is None:
                    import openai
                    self._openrouter_client = openai.OpenAI(
                        api_key=self.config.openrouter_api_key,
                        base_url=_OPENROUTER_BASE_URL,
                    )
        return self._openrouter_client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str = "text",
    ) -> str:
        """Send a prompt and return the response text.

        Retries up to 4 times with exponential backoff (2s, 4s, 8s, 16s)
        on rate-limit (429) and transient server errors (5xx).

        Args:
            system_prompt: System-level instructions.
            user_prompt: The user message / content to process.
            response_format: "text" or "json" (for JSON mode where supported).

        Returns:
            The model's response as a string.
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                if self.config.provider == "anthropic":
                    return self._complete_anthropic(system_prompt, user_prompt)
                elif self.config.provider == "openai":
                    return self._complete_openai(
                        system_prompt, user_prompt, response_format
                    )
                elif self.config.provider == "deepseek":
                    return self._complete_deepseek(
                        system_prompt, user_prompt, response_format
                    )
                elif self.config.provider == "gemini":
                    return self._complete_gemini(system_prompt, user_prompt)
                elif self.config.provider == "openrouter":
                    return self._complete_openrouter(
                        system_prompt, user_prompt, response_format
                    )
                else:
                    raise ValueError(f"Unknown provider: {self.config.provider}")
            except Exception as e:
                last_exc = e
                if attempt < _MAX_RETRIES and _is_retryable(e):
                    wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                    logger.warning(
                        "Retryable error (attempt %d/%d), waiting %ds: %s",
                        attempt + 1, _MAX_RETRIES, wait, e,
                    )
                    time.sleep(wait)
                    continue
                raise
        raise last_exc  # pragma: no cover  # type: ignore[misc]

    def _complete_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_anthropic()
        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def _complete_openai(
        self, system_prompt: str, user_prompt: str, response_format: str
    ) -> str:
        client = self._get_openai()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI returned empty content")
        return content

    def _complete_deepseek(
        self, system_prompt: str, user_prompt: str, response_format: str
    ) -> str:
        """Call DeepSeek API (OpenAI-compatible interface)."""
        client = self._get_deepseek()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("DeepSeek returned empty content")
        return content

    def _complete_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google Gemini API.

        Gemini combines system and user prompts into a single message with
        system instructions prepended.
        """
        model = self._get_gemini()
        # Gemini GenerativeModel supports system_instruction at construction
        # but we merge them here for simplicity since the model is cached.
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        import google.generativeai as genai  # type: ignore[import]
        generation_config = genai.GenerationConfig(
            max_output_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        response = model.generate_content(
            combined_prompt,
            generation_config=generation_config,
        )
        if not response.text:
            raise ValueError("Gemini returned empty content")
        return response.text

    def _complete_openrouter(
        self, system_prompt: str, user_prompt: str, response_format: str
    ) -> str:
        """Call OpenRouter API (OpenAI-compatible interface)."""
        client = self._get_openrouter()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenRouter returned empty content")
        return content

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Send a prompt expecting JSON response. Parses and returns dict."""
        # Do not force OpenAI-style ``json_object`` mode here.
        # Some pipeline stages (e.g., structural extraction) require a top-level
        # JSON array, which json_object mode disallows.
        raw = self.complete(system_prompt, user_prompt)

        # Extract JSON from response (handle markdown code blocks)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.strip().startswith("```") and not inside:
                    inside = True
                    continue
                elif line.strip() == "```" and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM returned invalid JSON: {text[:300]}..."
            ) from e
