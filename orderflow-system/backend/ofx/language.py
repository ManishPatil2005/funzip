"""Language policy: analytical, conditional, never an instruction to trade."""
from __future__ import annotations

import re

# Whole-word matches only: "buyers", "sellers" and "buyer-initiated" are allowed.
BANNED = re.compile(
    r"\b(buy|sell|hold|entry|enter|exit|target|stop[- ]?loss|guaranteed?|will|must|sure)\b",
    re.IGNORECASE,
)


class LanguagePolicyError(ValueError):
    pass


def lint(text: str) -> list[str]:
    """Return the banned terms found in text (empty list means compliant)."""
    return sorted({m.group(0).lower() for m in BANNED.finditer(text)})


def require_compliant(text: str) -> str:
    found = lint(text)
    if found:
        raise LanguagePolicyError(f"Text violates language policy: {found}")
    return text
