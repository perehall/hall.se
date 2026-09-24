-- Distinguish the current materialized plan from retained historical plan rows.
-- Historical rows remain queryable, while live/readback consumers can select
-- exactly one canonical snapshot through is_current.

alter table training.planned_workouts
  add column if not exists is_current boolean not null default false;

alter table training.planned_workouts
  add column if not exists last_seen_source_hash text;

create index if not exists planned_workouts_current_date_idx
  on training.planned_workouts (scheduled_date)
  where is_current;

comment on column training.planned_workouts.is_current is
  'True only when the workout belongs to the latest canonical shadow snapshot. Updated transactionally by the shadow writer.';

comment on column training.planned_workouts.last_seen_source_hash is
  'Canonical shadow source hash for the most recent snapshot in which this workout was present.';
