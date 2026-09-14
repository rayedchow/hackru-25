"""Deterministic deny, redaction, and retrieval rules."""

from __future__ import annotations

import re
import unicodedata

from .errors import ContentDenied

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[^\s,;]{6,}"
)
WORD_PATTERN = re.compile(r"[a-z0-9]{2,}")


def normalize_source(source: str | None) -> str:
    if not source:
        return "unknown"
    normalized = unicodedata.normalize("NFKC", source).strip().casefold()
    return normalized[:64] or "unknown"


def enforce_source_policy(source: str | None, denied_sources: tuple[str, ...]) -> str:
    normalized = normalize_source(source)
    if normalized in denied_sources:
        raise ContentDenied("Capture from this source is disabled by local policy.")
    return normalized


def redact_text(text: str, exclusion_terms: tuple[str, ...]) -> str:
    """Redact locally before text can be stored or sent to an optional provider."""
    value = unicodedata.normalize("NFKC", text)
    value = "".join(
        character if character in "\n\t" or character.isprintable() else " " for character in value
    )
    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    value = PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    value = TOKEN_PATTERN.sub("[REDACTED_SECRET]", value)
    for term in sorted(exclusion_terms, key=len, reverse=True):
        if term:
            value = re.sub(re.escape(term), "[REDACTED_USER_TERM]", value, flags=re.IGNORECASE)
    return value[:20_000]


def search_terms(text: str) -> set[str]:
    return set(WORD_PATTERN.findall(unicodedata.normalize("NFKC", text).casefold()))


def excerpt(text: str, terms: set[str], limit: int = 360) -> str:
    collapsed = " ".join(text.split())
    if not collapsed:
        return "No OCR text was extracted."
    folded = collapsed.casefold()
    positions = [folded.find(term) for term in sorted(terms) if folded.find(term) >= 0]
    start = max(0, min(positions, default=0) - 80)
    value = collapsed[start : start + limit]
    if start:
        value = "…" + value
    if start + limit < len(collapsed):
        value += "…"
    return value
