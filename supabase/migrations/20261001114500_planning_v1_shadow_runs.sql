-- Planning Engine v1 shadow-run audit log.
-- Append-only evidence only: this table is deliberately not planning authority
-- and has no trigger/function/foreign key that can mutate current planned workouts.

create table training.planning_v1_shadow_runs (
  id uuid primary key default gen_random_uuid(),
  event_key text,
  trigger_source text not null,
  microcycle_key text,
  source_revision text not null,
  semantic_input_hash text,
  strategy_revision_id text,
  engine_version text,
  affected_from date not null,
  affected_until date not null,
  readiness_status text not null
    check (readiness_status in ('ready', 'blocked')),
  blocker_codes text[] not null default '{}'::text[],
  solver_status text
    check (solver_status is null or solver_status in ('current', 'blocked')),
  plan_content_hash text,
  semantic_input jsonb,
  plan_content jsonb,
  objective_vector jsonb,
  decision_trace jsonb not null default '{}'::jsonb
    check (jsonb_typeof(decision_trace) = 'object'),
  created_at timestamptz not null default now(),
  check (affected_until >= affected_from),
  check (
    (readiness_status = 'blocked'
      and solver_status is null
      and semantic_input_hash is null
      and plan_content_hash is null
      and semantic_input is null
      and plan_content is null
      and objective_vector is null)
    or
    (readiness_status = 'ready' and solver_status is not null)
  ),
  check (
    (solver_status = 'current'
      and plan_content_hash is not null
      and plan_content is not null
      and objective_vector is not null)
    or
    (solver_status = 'blocked'
      and plan_content_hash is null
      and plan_content is null
      and objective_vector is null)
    or
    solver_status is null
  )
);

comment on table training.planning_v1_shadow_runs is
  'Append-only non-authoritative Planning Engine v1 shadow evidence. Rows record exact semantic input/output/trace for replay and cutover review; they never publish training content.';

comment on column training.planning_v1_shadow_runs.semantic_input is
  'Canonical semantic planning input payload used for deterministic replay. NULL when readiness blocks before solver execution.';

comment on column training.planning_v1_shadow_runs.decision_trace is
  'Machine-readable readiness/solver decision trace. This is audit evidence, not a source of planning authority.';

create unique index planning_v1_shadow_runs_event_engine_uidx
  on training.planning_v1_shadow_runs (event_key, engine_version)
  where event_key is not null and engine_version is not null;

create index planning_v1_shadow_runs_created_idx
  on training.planning_v1_shadow_runs (created_at desc);

create index planning_v1_shadow_runs_microcycle_created_idx
  on training.planning_v1_shadow_runs (microcycle_key, created_at desc);

create index planning_v1_shadow_runs_source_revision_idx
  on training.planning_v1_shadow_runs (source_revision, created_at desc);

alter table training.planning_v1_shadow_runs enable row level security;
revoke all on table training.planning_v1_shadow_runs from anon, authenticated;
grant all on table training.planning_v1_shadow_runs to service_role;
