from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path("prompts/pr_review_system_prompt.md")


class LLMReviewProvider:
    """Generate PR review markdown from collected evidence."""

    def __init__(
        self,
        http_post: Callable[..., Any] | None = None,
        prompt_path: str | os.PathLike[str] = DEFAULT_PROMPT_PATH,
    ) -> None:
        self.http_post = http_post or requests.post
        self.prompt_path = Path(prompt_path)
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self.timeout = int(os.getenv("LLM_REVIEW_TIMEOUT", "120"))

    def generate_pr_review(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "anthropic":
            return self._generate_with_anthropic(context)
        if self.provider == "openai":
            return self._generate_with_openai(context)
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {self.provider}")

    def _generate_with_openai(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")

        prompt = self._build_prompt(context)
        response = self.http_post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.openai_model,
                "input": prompt,
            },
            timeout=self.timeout,
        )
        self._raise_for_status(response, "OpenAI")
        data = response.json()
        text = self._extract_openai_text(data)
        if not text:
            raise RuntimeError(f"No review text returned from OpenAI: {data}")

        return {
            "provider": "openai",
            "model": self.openai_model,
            "review_markdown": text,
            "raw_response": data,
        }

    def _generate_with_anthropic(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is missing")

        prompt = self._build_prompt(context)
        response = self.http_post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.anthropic_model,
                "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4000")),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        self._raise_for_status(response, "Anthropic")
        data = response.json()
        text = self._extract_anthropic_text(data)
        if not text:
            raise RuntimeError(f"No review text returned from Anthropic: {data}")

        return {
            "provider": "anthropic",
            "model": self.anthropic_model,
            "review_markdown": text,
            "raw_response": data,
        }

    def _build_prompt(self, context: dict[str, Any]) -> str:
        system_prompt = self._load_prompt()
        return (
            f"{system_prompt}\n\n"
            "Use the following MCP review context as your only evidence.\n"
            "Return only the review markdown in the requested format.\n\n"
            f"{json.dumps(context, indent=2, default=str)}"
        )

    def _load_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Prompt file not found: %s", self.prompt_path)
            return (
                "You are the BuildProcure Senior PR Review Agent. "
                "Review only from the provided evidence and return concise markdown."
            )

    def _extract_openai_text(self, data: dict[str, Any]) -> str:
        if data.get("output_text"):
            return str(data["output_text"]).strip()

        text_parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
        return "\n".join(text_parts).strip()

    def _extract_anthropic_text(self, data: dict[str, Any]) -> str:
        text_parts = []
        for content in data.get("content", []):
            if content.get("type") == "text":
                text_parts.append(content.get("text", ""))
        return "\n".join(text_parts).strip()

    def _raise_for_status(self, response: Any, provider: str) -> None:
        if response.status_code >= 400:
            logger.error("%s error: %s", provider, response.text)
        response.raise_for_status()
