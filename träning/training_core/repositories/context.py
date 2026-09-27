"""Repository port for canonical mesocycle/microcycle context."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from training_core.domain.planning import (
    MesocycleContext,
    MicrocycleContext,
    WeekPlanningContext,
)


class PlanningContextRepository(Protocol):
    def week_context(self, week_start: date) -> WeekPlanningContext | None: ...


@dataclass
class PostgresPlanningContextRepository:
    connection_factory: object

    @classmethod
    def from_environment(cls) -> "PostgresPlanningContextRepository":
        import psycopg

        url = str(os.environ.get("SUPABASE_DB_URL") or "").strip()
        if not url:
            raise RuntimeError("SUPABASE_DB_URL is missing")
        return cls(
            lambda: psycopg.connect(url, sslmode="require", connect_timeout=15)
        )

    def week_context(self, week_start: date) -> WeekPlanningContext | None:
        query = """
            select mc.id, mc.mesocycle_id, mc.microcycle_index, mc.week_start,
                   coalesce(mc.rationale,''), coalesce(mc.payload,'{}'::jsonb),
                   m.id, m.title, coalesce(m.decision,''), m.start_date, m.end_date,
                   m.duration_weeks, coalesce(m.goal_contribution,''),
                   coalesce(m.hypothesis,''), coalesce(m.payload,'{}'::jsonb)
            from training.microcycles mc
            join training.mesocycles m on m.id = mc.mesocycle_id
            where mc.week_start = %s
            order by mc.updated_at desc
            limit 1
        """
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(query, (week_start,))
            row = cur.fetchone()
        if row is None:
            return None
        return WeekPlanningContext(
            microcycle=MicrocycleContext(
                microcycle_id=row[0],
                mesocycle_id=row[1],
                microcycle_index=row[2],
                week_start=row[3],
                rationale=row[4] or "",
                payload=row[5] or {},
            ),
            mesocycle=MesocycleContext(
                mesocycle_id=row[6],
                title=row[7],
                decision=row[8] or "",
                start_date=row[9],
                end_date=row[10],
                duration_weeks=row[11],
                goal_contribution=row[12] or "",
                hypothesis=row[13] or "",
                payload=row[14] or {},
            ),
        )
