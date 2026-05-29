"""Claude API wrapper for ideation, script, SEO, translation. Prompt caching enabled."""
from __future__ import annotations

import os

from ..models import Language, SeoMeta


class ClaudeClient:
    def __init__(self, model: str = "claude-opus-4-7",
                 api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

    def _client(self):
        from anthropic import Anthropic
        return Anthropic(api_key=self.api_key)

    def generate_seo(self, theme: str, language: Language,
                     title_template: str) -> SeoMeta:
        # TODO: real prompt; ask for title/description/tags/chapters as JSON.
        raise NotImplementedError("generate_seo: wire Claude messages.create with caching")

    def translate(self, text: str, frm: Language, to: Language) -> str:
        raise NotImplementedError("translate: used by dubbing fallback path")
