"""Typed factual manual activities embedded in canonical planned-workout payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from training_core.presentation.public_copy import public_reason
from training_core.presentation.sport_identity import sport_icon_key

if TYPE_CHECKING:
    from training_core.presentation.today import PlannedDay


VALID_CLASSIFICATIONS = {"training", "recreation"}


@dataclass(frozen=True)
class ManualActivityReadModel:
    session: str
    sport: str
    classification: str
    reason: str
    icon_key: str

    @property
    def classification_label(self) -> str:
        return "Träning" if self.classification == "training" else "Rekreation"


def manual_activities_for_day(
    day: "PlannedDay",
) -> tuple[ManualActivityReadModel, ...]:
    payload = day.payload or {}
    raw = payload.get("manual_activities") or []
    if not isinstance(raw, list):
        raise RuntimeError(
            f"manual_activities must be a list for {day.local_date.isoformat()}"
        )

    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuntimeError(
                f"manual activity {index} must be an object for "
                f"{day.local_date.isoformat()}"
            )
        status = str(item.get("status") or "").strip().lower()
        sport = str(item.get("sport") or "").strip().lower()
        session = str(item.get("session") or "").strip()
        classification = str(
            item.get("classification") or "training"
        ).strip().lower()
        if status != "completed":
            raise RuntimeError(
                f"manual activity {index} is not completed for "
                f"{day.local_date.isoformat()}"
            )
        if not sport or not session:
            raise RuntimeError(
                f"manual activity {index} lacks sport/session for "
                f"{day.local_date.isoformat()}"
            )
        if classification not in VALID_CLASSIFICATIONS:
            raise RuntimeError(
                f"manual activity {index} has invalid classification "
                f"{classification!r}"
            )
        result.append(
            ManualActivityReadModel(
                session=session,
                sport=sport,
                classification=classification,
                reason=public_reason(
                    str(item.get("reason") or ""),
                    max_chars=320,
                ),
                icon_key=sport_icon_key(sport) or "activity",
            )
        )
    return tuple(result)
