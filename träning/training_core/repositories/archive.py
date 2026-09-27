"""Adapters for published-week metadata and immutable historical audit artifacts.

The archive JSON files are explicit audit/export artifacts created by the
legacy system. They are isolated behind this adapter and never exposed to
presentation code as raw dictionaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, Sequence

from training_core.domain.history import (
    ArchivedActivity,
    ArchivedCoachEvaluation,
    ArchivedPlanDay,
    ArchivedWeek,
    ArchivedWeekReview,
)
from training_core.presentation.navigation import PublishedWeek


PUBLIC_LABELS = {
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "MountainBikeRide": "MTB/XC",
    "EMountainBikeRide": "Enduro",
    "WeightTraining": "Styrka",
    "StrengthTraining": "Styrka",
    "Enduro": "Enduro",
}


def _public_label(label: str, sport_type: str) -> str:
    raw = str(label or "").strip()
    sport = str(sport_type or "").strip()
    if raw and raw not in PUBLIC_LABELS:
        return raw
    return PUBLIC_LABELS.get(raw, PUBLIC_LABELS.get(sport, raw or sport or "Träning"))


def _clean_strings(values) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


class WeekArchiveRepository(Protocol):
    def published_weeks(self) -> Sequence[PublishedWeek]: ...
    def current_published_week(self) -> PublishedWeek: ...
    def archived_week(self, key: str) -> ArchivedWeek: ...


@dataclass(frozen=True)
class ManifestWeekArchiveRepository:
    path: Path
    snapshots_dir: Path | None = None
    reviews_dir: Path | None = None

    @property
    def _snapshots_dir(self) -> Path:
        return self.snapshots_dir or self.path.parent

    @property
    def _reviews_dir(self) -> Path:
        return self.reviews_dir or self.path.parent.parent / "week_reviews"

    def _manifest(self) -> dict:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 2:
            raise RuntimeError("unsupported week archive manifest")
        return document

    def published_weeks(self) -> list[PublishedWeek]:
        document = self._manifest()
        if document.get("schema_version") != 2:
            raise RuntimeError("unsupported week archive manifest")
        result = []
        for row in document.get("weeks") or []:
            key = str(row.get("key") or "").strip()
            start = date.fromisoformat(str(row.get("week_start") or ""))
            end = date.fromisoformat(str(row.get("week_end") or ""))
            url = str(row.get("url") or "").strip()
            if not key or not url or (end - start).days != 6:
                raise RuntimeError(f"invalid week archive manifest row: {row!r}")
            result.append(
                PublishedWeek(
                    key=key,
                    week_start=start,
                    week_end=end,
                    url=url,
                )
            )
        return result

    def current_published_week(self) -> PublishedWeek:
        document = self._manifest()
        current_key = str(document.get("current_week_key") or "").strip()
        if not current_key:
            raise RuntimeError("week archive manifest missing current_week_key")
        current = next(
            (row for row in self.published_weeks() if row.key == current_key),
            None,
        )
        if current is None:
            raise RuntimeError(
                f"week archive manifest current week not published: {current_key}"
            )
        return current

    def archived_week(self, key: str) -> ArchivedWeek:
        snapshot_path = self._snapshots_dir / f"{key}.json"
        if not snapshot_path.exists():
            raise KeyError(f"archived week not found: {key}")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if snapshot.get("schema_version") != 1 or snapshot.get("week_key") != key:
            raise RuntimeError(f"invalid archived week snapshot: {key}")

        start = date.fromisoformat(str(snapshot.get("week_start") or ""))
        end = date.fromisoformat(str(snapshot.get("week_end") or ""))
        if (end - start).days != 6:
            raise RuntimeError(f"archived week is not seven days: {key}")

        plan = snapshot.get("plan") or {}
        plan_meta = plan.get("meta") or {}
        plan_days = []
        for row in plan.get("days") or []:
            local_date = date.fromisoformat(str(row.get("date") or ""))
            plan_days.append(
                ArchivedPlanDay(
                    local_date=local_date,
                    session=str(row.get("session") or "").strip(),
                    status=str(row.get("status") or "").strip(),
                    planning_status=str(row.get("planning_status") or "").strip(),
                    manual_lock=bool(row.get("manual_lock")),
                    reason=str(row.get("reason") or "").strip(),
                    development_focus=str(row.get("development_focus") or "").strip(),
                    payload=dict(row),
                )
            )

        activities = []
        for row in snapshot.get("activities") or []:
            value = str(row.get("start_date_local") or row.get("date") or "")[:10]
            if not value:
                continue
            activity_date = date.fromisoformat(value)
            source_id = row.get("id")
            if source_id is None:
                continue
            sport_type = str(row.get("sport_type") or row.get("source_sport_type") or "").strip()
            activities.append(
                ArchivedActivity(
                    provider_activity_id=str(source_id),
                    local_date=activity_date,
                    label=_public_label(row.get("display_label") or row.get("label") or sport_type, sport_type),
                    sport_type=sport_type,
                    classification=str(row.get("classification") or "training").strip(),
                    elapsed_time_s=row.get("elapsed_time_s"),
                    distance_m=row.get("distance_m"),
                    average_heartrate=row.get("average_heartrate"),
                    max_heartrate=row.get("max_heartrate"),
                    user_report=str(row.get("user_report") or "").strip(),
                )
            )

        evaluations = []
        for row in snapshot.get("coach_analyses") or []:
            source_id = row.get("activity_id")
            activity_date_text = str(row.get("activity_date") or "").strip()
            if source_id is None or not activity_date_text:
                continue
            assessment = row.get("assessment") or {}
            action = row.get("plan_action") or {}
            auto_apply = row.get("auto_apply") or {}
            evaluations.append(
                ArchivedCoachEvaluation(
                    provider_activity_id=str(source_id),
                    activity_date=date.fromisoformat(activity_date_text),
                    generated_at_utc=str(row.get("generated_at_utc") or ""),
                    summary=str(assessment.get("summary") or "").strip(),
                    interpretations=_clean_strings(assessment.get("interpretations")),
                    unknowns=_clean_strings(assessment.get("unknowns")),
                    plan_action=str(action.get("action") or "").strip(),
                    action_reason=str(action.get("reason") or "").strip(),
                    recommendation=str(action.get("recommendation") or "").strip(),
                    auto_applied=bool(auto_apply.get("applied")),
                )
            )

        review = self._load_review(key)
        return ArchivedWeek(
            key=key,
            start=start,
            end=end,
            title=str(plan_meta.get("title") or "").strip(),
            principle=str(plan_meta.get("principle") or "").strip(),
            plan_days=tuple(sorted(plan_days, key=lambda item: item.local_date)),
            activities=tuple(
                sorted(activities, key=lambda item: (item.local_date, item.provider_activity_id))
            ),
            coach_evaluations=tuple(
                sorted(
                    evaluations,
                    key=lambda item: (
                        item.activity_date,
                        item.provider_activity_id,
                        item.generated_at_utc,
                    ),
                )
            ),
            review=review,
        )

    def _load_review(self, key: str) -> ArchivedWeekReview | None:
        review_path = self._reviews_dir / f"{key}.json"
        if not review_path.exists():
            return None
        document = json.loads(review_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1 or document.get("week_key") != key:
            raise RuntimeError(f"invalid archived week review: {key}")
        facts = document.get("facts") or {}
        assessment = document.get("assessment") or {}
        return ArchivedWeekReview(
            activity_count=int(facts.get("activity_count") or 0),
            training_activity_count=int(facts.get("training_activity_count") or 0),
            recreation_activity_count=int(facts.get("recreation_activity_count") or 0),
            active_days=int(facts.get("active_days") or 0),
            total_activity_time_s=int(facts.get("total_activity_time_s") or 0),
            summary=str(assessment.get("summary") or "").strip(),
            worked=_clean_strings(assessment.get("worked")),
            not_as_planned=_clean_strings(assessment.get("not_as_planned")),
            load_continuity=str(assessment.get("load_continuity") or "").strip(),
            key_lesson=str(assessment.get("key_lesson") or "").strip(),
            next_week_implication=str(assessment.get("next_week_implication") or "").strip(),
            uncertainties=_clean_strings(assessment.get("uncertainties")),
        )
