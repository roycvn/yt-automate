"""SEO + monetization-friendly metadata — niche-agnostic.

Builds a keyword-rich description (keywords, hashtags, CTA) and a deduped tag
list from the generated script's own title/description/tags plus optional
channel-level evergreen tags. No niche assumptions baked in.
"""
from __future__ import annotations

import re


def _hashtags(tags: list[str], limit: int = 6) -> str:
    out = []
    for t in tags:
        h = re.sub(r"[^0-9A-Za-zऀ-ॿఀ-౿]", "", t.title().replace(" ", ""))
        if h:
            out.append("#" + h)
        if len(out) >= limit:
            break
    return " ".join(out)


def build_description(title: str, title_translit: str, base_desc: str,
                      tags: list[str], channel: dict | None = None) -> str:
    channel = channel or {}
    name = channel.get("name", "our channel")
    cta = channel.get("cta", "🔔 Subscribe & hit the bell for new videos every week!\n👍 Like & share if you enjoyed.")
    keywords = ", ".join(dict.fromkeys(tags))
    return (
        f"{base_desc}\n\n"
        f"{title}" + (f" ({title_translit})" if title_translit and title_translit != title else "") + "\n\n"
        f"{cta}\n\n"
        f"🔎 {keywords}\n\n"
        f"{_hashtags(tags)}"
    )


def build_tags(tags: list[str], base_tags: list[str] | None = None) -> list[str]:
    """Merge script tags with optional channel evergreen tags; dedup; cap (<500 chars)."""
    merged = list(dict.fromkeys([*tags, *(base_tags or [])]))
    out, total = [], 0
    for t in merged:
        if total + len(t) + 1 > 480 or len(out) >= 30:
            break
        out.append(t)
        total += len(t) + 1
    return out
