"""Repository ports and PostgreSQL implementation for presentation state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from training_core.presentation.today import CompletedActivity, PlannedDay


PUBLIC_ACTIVITY_LABELS = {
    "run": "Löpning",
    "swim": "Simning",
    "bike": "Cykel",
    "mtb": "MTB/XC",
    "MountainBikeRide": "MTB/XC",
    "EMountainBikeRide": "MTB/XC",
    "enduro": "Enduro",
    "strength": "Styrka",
    "Run": "Löpning",
    "TrailRun": "Löpning",
    "VirtualRun": "Löpning",
    "Swim": "Simning",
    "Ride": "Cykel",
    "VirtualRide": "Cykel",
    "MountainBikeRide": "MTB/XC",
    "WeightTraining": "Styrka",
    "StrengthTraining": "Styrka",
}


def public_activity_label(label: str, sport_family: str) -> str:
    raw = str(label or "").strip()
    family = str(sport_family or "").strip()
    if raw and raw not in PUBLIC_ACTIVITY_LABELS:
        return raw
    return PUBLIC_ACTIVITY_LABELS.get(raw, PUBLIC_ACTIVITY_LABELS.get(family, raw or family or "Träning"))


class PresentationRepository(Protocol):
    def planned_days(self, start: date, end: date) -> Sequence[PlannedDay]: ...
    def completed_activities(self, start: date, end: date) -> Sequence[CompletedActivity]: ...


@dataclass
class PostgresPresentationRepository:
    connection_factory: object

    @classmethod
    def from_environment(cls) -> "PostgresPresentationRepository":
        import psycopg
        url = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
        if not url:
            raise RuntimeError("SUPABASE_DB_URL is missing")
        return cls(lambda: psycopg.connect(url, sslmode="require", connect_timeout=15))

    def planned_days(self, start: date, end: date) -> list[PlannedDay]:
        query = """
            select scheduled_date, session, coalesce(sport,''), coalesce(status,''),
                   coalesce(planning_status,''), coalesce(manual_lock,false),
                   coalesce(reason,''), coalesce(development_focus,''),
                   coalesce(payload,'{}'::jsonb)
            from training.planned_workouts
            where is_current
              and scheduled_date between %s and %s
            order by scheduled_date, workout_key
        """
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(query, (start, end))
            rows = cur.fetchall()
        return [
            PlannedDay(
                local_date=row[0], session=row[1], sport=row[2], status=row[3],
                planning_status=row[4], manual_lock=bool(row[5]),
                reason=row[6], development_focus=row[7], payload=row[8] or {},
            )
            for row in rows
        ]

    def completed_activities(self, start: date, end: date) -> list[CompletedActivity]:
        query = """
            select a.provider_activity_id, a.local_date,
                   coalesce(o.display_label, a.display_label, a.sport_family, a.sport_type),
                   coalesce(a.sport_family, a.sport_type),
                   a.elapsed_time_s, a.distance_m
            from training.activities a
            left join training.activity_overrides o on o.activity_id = a.id
            where a.local_date between %s and %s
              and coalesce(o.classification, a.classification, 'training') <> 'recreation'
            order by a.started_at, a.provider_activity_id
        """
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(query, (start, end))
            rows = cur.fetchall()
        return [
            CompletedActivity(
                provider_activity_id=str(row[0]), local_date=row[1],
                label=public_activity_label(row[2], row[3]),
                sport_family=row[3], elapsed_time_s=row[4], distance_m=row[5],
            )
            for row in rows
        ]
