"""Public-copy boundary for presentation-derived training prose.

Canonical planning state may contain machine-oriented provenance or internal
decision-trace vocabulary. Presentation must never expose those implementation
details merely because they are stored in the same source field.
"""

from __future__ import annotations

import re


INTERNAL_MARKERS = (
    " Valet utgår från",
    " Veckobeslut:",
    " materialiserad relation:",
    " Katalogen innehåller",
)

INTERNAL_TOKENS = (
    "athlete_state",
    "dose_option_id",
    "materialized relation",
    "materialiserad relation",
    "mesocycle_contract",
    "microcycle_contract",
    "selected_candidate_id",
    "deterministic_constraint",
)


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def public_reason(value: str, *, max_chars: int = 220) -> str:
    """Return user-facing reason text without internal planning provenance.

    The function only removes machine-oriented material; it does not invent a
    replacement explanation when the canonical field contains no public copy.
    """
    text = _plain(value)
    if not text:
        return ""

    for marker in INTERNAL_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0].strip()

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]
    public_sentences = [
        sentence
        for sentence in sentences
        if not any(token in sentence.lower() for token in INTERNAL_TOKENS)
    ]
    text = " ".join(public_sentences[:2]).strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    clipped = text[: max_chars - 1].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


def assert_public_copy(value: str) -> None:
    lowered = _plain(value).lower()
    leaked = [token for token in INTERNAL_TOKENS if token in lowered]
    if leaked:
        raise RuntimeError(
            "internal planning vocabulary leaked to public copy: "
            + ", ".join(sorted(leaked))
        )
