"""Stage 06 — SEO. Generate title/description/tags/chapters per language via Claude."""
from __future__ import annotations

from ..clients.claude import ClaudeClient
from ..models import Language, SeoMeta


def run(theme: str, language: Language, claude: ClaudeClient,
        title_template: str) -> SeoMeta:
    return claude.generate_seo(theme, language, title_template)
