from __future__ import annotations

import pytest

from utils.llm_review_provider import LLMReviewProvider


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self.data = data
        self.status_code = status_code
        self.text = str(data)

    def json(self) -> dict:
        return self.data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text)


def test_openai_provider_extracts_review_markdown(monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Review prompt", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse({"output": [{"content": [{"type": "output_text", "text": "## Review"}]}]})

    result = LLMReviewProvider(http_post=fake_post, prompt_path=prompt_path).generate_pr_review({"ok": True})

    assert result["provider"] == "openai"
    assert result["review_markdown"] == "## Review"
    assert calls[0]["json"]["model"]


def test_anthropic_provider_extracts_review_markdown(monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Review prompt", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fake_post(*args, **kwargs):
        return FakeResponse({"content": [{"type": "text", "text": "## Claude Review"}]})

    result = LLMReviewProvider(http_post=fake_post, prompt_path=prompt_path).generate_pr_review({"ok": True})

    assert result["provider"] == "anthropic"
    assert result["review_markdown"] == "## Claude Review"


def test_provider_rejects_missing_openai_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        LLMReviewProvider(http_post=lambda *args, **kwargs: None).generate_pr_review({"ok": True})
