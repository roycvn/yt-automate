"""SEO + monetization-friendly metadata for the upload.

Builds a keyword-rich description (search keywords, hashtags, CTA, chapters
placeholder) and a deduped tag list from the generated script's title/tags.
Designed for the Hindi/Telugu animated-horror niche.
"""
from __future__ import annotations

# Evergreen niche keywords appended to every video's tag set for reach.
BASE_TAGS = [
    "horror story", "hindi horror story", "animated horror", "bhoot ki kahani",
    "chudail ki kahani", "scary stories", "horror kahani", "हिंदी हॉरर कहानी",
    "डरावनी कहानी", "भूत की कहानी", "animated horror stories hindi",
    "moral story", "horror cartoon", "ghost story hindi",
]

CTA = (
    "🔔 चैनल को SUBSCRIBE करें और घंटी दबाएँ — हर हफ़्ते नई डरावनी कहानी!\n"
    "👍 वीडियो पसंद आए तो LIKE करें और दोस्तों के साथ SHARE करें।"
)


def build_description(title_hi: str, title_translit: str, base_desc: str,
                      tags: list[str], language: str = "hi") -> str:
    """Compose a keyword-rich, monetization-friendly description."""
    keywords = ", ".join(dict.fromkeys(tags + BASE_TAGS))
    hashtags = " ".join(
        "#" + t.replace(" ", "").replace("ी", "i")  # ascii-ish hashtags help discovery
        for t in ["HorrorStory", "HindiHorror", "BhootKiKahani", "ChudailKiKahani",
                  "AnimatedHorror", "ScaryStories", "HindiKahaniya"]
    )
    return (
        f"{base_desc}\n\n"
        f"{title_hi} ({title_translit}) — एक नई एनिमेटेड हॉरर कहानी।\n\n"
        f"{CTA}\n\n"
        f"इस कहानी में: {title_hi}. अगर आपको डरावनी कहानियाँ, भूत-प्रेत, चुड़ैल और "
        f"रहस्यमयी कहानियाँ पसंद हैं तो यह चैनल आपके लिए है।\n\n"
        f"🔎 Keywords: {keywords}\n\n"
        f"{hashtags}"
    )


def build_tags(tags: list[str]) -> list[str]:
    """Merge script tags with evergreen niche tags, dedup, cap at 30 (~500 char)."""
    merged = list(dict.fromkeys([*tags, *BASE_TAGS]))
    out, total = [], 0
    for t in merged:
        if total + len(t) + 1 > 480 or len(out) >= 30:
            break
        out.append(t)
        total += len(t) + 1
    return out
