import re


def clean_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def normalize_job(raw: dict, source: str) -> dict:
    """Normalize a raw job dict from any source into a common schema."""
    return {
        "source": source,
        "title": raw.get("title", ""),
        "company": raw.get("company", ""),
        "location": raw.get("location", ""),
        "url": raw.get("url", ""),
        "description": clean_html(raw.get("description", "")),
        "posted_at": raw.get("posted_at", ""),
        "analysis": None,
    }
