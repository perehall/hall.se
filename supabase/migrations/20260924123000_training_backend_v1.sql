-- hall-training backend v1
-- Phase 1: shadow schema only. The existing JSON/GitHub pipeline remains source-of-truth.
-- No client policies are created; tables are backend-only until a later migration.

create extension if not exists pgcrypto with schema extensions;

create schema if not exists training;

comment on schema training is
  'Domain data for the hall.se training system. Phase 1 is a read/write shadow of the canonical GitHub JSON state.';

create or replace function training.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table training.activities (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  provider_activity_id text not null,
  name text,
  sport_type text not null,
  source_sport_type text,
  sport_family text,
  display_label text,
  classification text,
  started_at timestamptz not null,
  local_date date not null,
  timezone text not null default 'Europe/Stockholm',
  distance_m double precision check (distance_m is null or distance_m >= 0),
  moving_time_s integer check (moving_time_s is null or moving_time_s >= 0),
  elapsed_time_s integer check (elapsed_time_s is null or elapsed_time_s >= 0),
  total_elevation_gain_m double precision check (total_elevation_gain_m is null or total_elevation_gain_m >= 0),
  average_heartrate double precision check (average_heartrate is null or average_heartrate >= 0),
  max_heartrate double precision check (max_heartrate is null or max_heartrate >= 0),
  average_watts double precision,
  weighted_average_watts double precision,
  calories double precision check (calories is null or calories >= 0),
  device_name text,
  gear_id text,
  gear_name text,
  plan_relation text,
  raw jsonb not null default '{}'::jsonb check (jsonb_typeof(raw) = 'object'),
  source_updated_at timestamptz,
  imported_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_activity_id)
);

comment on table training.activities is
  'Normalized activity facts. provider/provider_activity_id is the stable idempotency key; raw preserves unmodeled source fields.';

create index activities_local_date_idx
  on training.activities (local_date desc);
create index activities_started_at_idx
  on training.activities (started_at desc);
create index activities_family_date_idx
  on training.activities (sport_family, local_date desc);

create table training.activity_laps (
  activity_id uuid not null references training.activities(id) on delete cascade,
  lap_index integer not null check (lap_index >= 0),
  name text,
  elapsed_time_s integer check (elapsed_time_s is null or elapsed_time_s >= 0),
  moving_time_s integer check (moving_time_s is null or moving_time_s >= 0),
  distance_m double precision check (distance_m is null or distance_m >= 0),
  average_speed_mps double precision,
  average_heartrate double precision,
  max_heartrate double precision,
  average_watts double precision,
  average_cadence double precision,
  raw jsonb not null default '{}'::jsonb check (jsonb_typeof(raw) = 'object'),
  primary key (activity_id, lap_index)
);

create table training.activity_feedback (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references training.activities(id) on delete cascade,
  source text not null default 'user',
  operation text,
  feedback_text text,
  rpe smallint check (rpe is null or rpe between 1 and 10),
  feeling text[] not null default '{}'::text[],
  event_key text,
  submitted_at timestamptz,
  raw jsonb not null default '{}'::jsonb check (jsonb_typeof(raw) = 'object'),
  created_at timestamptz not null default now()
);

comment on table training.activity_feedback is
  'Append-only user feedback/history. Unlike activity_overrides this table must not collapse successive reports into one string.';

create unique index activity_feedback_event_key_uidx
  on training.activity_feedback (event_key)
  where event_key is not null;
create index activity_feedback_activity_created_idx
  on training.activity_feedback (activity_id, created_at desc);

create table training.activity_overrides (
  activity_id uuid primary key references training.activities(id) on delete cascade,
  sport_type text,
  classification text,
  display_label text,
  source_sport_type text,
  garmin_activity_type text,
  plan_relation text,
  user_report text,
  reason text,
  raw jsonb not null default '{}'::jsonb check (jsonb_typeof(raw) = 'object'),
  updated_at timestamptz not null default now()
);

comment on table training.activity_overrides is
  'Current semantic correction for an activity. Historical subjective input belongs in activity_feedback.';

create table training.training_goals (
  goal_id text primary key,
  goal_type text not null,
  role text,
  status text not null default 'active',
  title text not null,
  objective text,
  event_name text,
  event_date date,
  sport text,
  target text,
  priority_class text,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz not null default now()
);

create index training_goals_status_type_idx
  on training.training_goals (status, goal_type);

create table training.state_documents (
  document_key text primary key,
  schema_version integer,
  generated_at timestamptz,
  source_hash text,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  updated_at timestamptz not null default now()
);

comment on table training.state_documents is
  'Compatibility bridge for generated documents whose relational shape is still evolving, e.g. athlete_state and planning policy.';

create table training.mesocycles (
  id text primary key,
  title text not null,
  decision text,
  start_date date not null,
  end_date date not null,
  evaluation_date date,
  duration_weeks smallint check (duration_weeks is null or duration_weeks > 0),
  goal_contribution text,
  hypothesis text,
  source text,
  source_hash text,
  goal_hash text,
  generated_at timestamptz,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date >= start_date)
);

create index mesocycles_date_idx
  on training.mesocycles (start_date desc, end_date desc);

create table training.microcycles (
  id text primary key,
  mesocycle_id text not null references training.mesocycles(id) on delete restrict,
  microcycle_index smallint check (microcycle_index is null or microcycle_index > 0),
  week_start date not null,
  week_key text,
  rationale text,
  planner_revision integer,
  source text,
  source_hash text,
  generated_at timestamptz,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index microcycles_mesocycle_week_idx
  on training.microcycles (mesocycle_id, week_start desc);

create table training.planned_workouts (
  id uuid primary key default gen_random_uuid(),
  workout_key text not null unique,
  mesocycle_id text references training.mesocycles(id) on delete restrict,
  microcycle_id text references training.microcycles(id) on delete restrict,
  scheduled_date date not null,
  microcycle_day smallint check (microcycle_day is null or microcycle_day > 0),
  slot_key text,
  sport text,
  classification text,
  status text,
  planning_status text,
  session text not null,
  priority_role text,
  manual_lock boolean not null default false,
  reason text,
  development_focus text,
  stimuli text[] not null default '{}'::text[],
  linked_activity_id uuid references training.activities(id) on delete set null,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table training.planned_workouts is
  'Current materialized workout state. workout_key is assigned deterministically by the importer/planner; revisions are append-only.';

create index planned_workouts_date_idx
  on training.planned_workouts (scheduled_date);
create index planned_workouts_microcycle_idx
  on training.planned_workouts (microcycle_id, scheduled_date);

create table training.planned_workout_revisions (
  id uuid primary key default gen_random_uuid(),
  workout_id uuid not null references training.planned_workouts(id) on delete cascade,
  revision_no integer not null check (revision_no > 0),
  changed_at timestamptz not null default now(),
  source text not null,
  change_kind text,
  reason text,
  before_state jsonb,
  after_state jsonb not null check (jsonb_typeof(after_state) = 'object'),
  unique (workout_id, revision_no)
);

create index workout_revisions_workout_changed_idx
  on training.planned_workout_revisions (workout_id, changed_at desc);

create table training.coach_evaluations (
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references training.activities(id) on delete cascade,
  generated_at timestamptz not null,
  model text,
  confidence text,
  summary text,
  load_interpretation text,
  plan_action text,
  target_date date,
  action_reason text,
  recommendation text,
  requires_approval boolean not null default false,
  auto_applied boolean not null default false,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  unique (activity_id, generated_at)
);

create index coach_evaluations_activity_generated_idx
  on training.coach_evaluations (activity_id, generated_at desc);

create table training.planning_decisions (
  id uuid primary key default gen_random_uuid(),
  scope_type text not null,
  scope_key text not null,
  action text not null,
  reason text,
  source text,
  generated_at timestamptz not null default now(),
  evidence jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object')
);

create index planning_decisions_scope_generated_idx
  on training.planning_decisions (scope_type, scope_key, generated_at desc);

create table training.integration_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_key text not null,
  event_type text,
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  status text not null default 'received'
    check (status in ('received', 'processing', 'processed', 'failed', 'ignored')),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  error_message text,
  unique (provider, event_key)
);

create index integration_events_status_received_idx
  on training.integration_events (status, received_at desc);

create table training.integration_sync_state (
  provider text primary key,
  status text not null default 'unknown',
  cursor jsonb not null default '{}'::jsonb check (jsonb_typeof(cursor) = 'object'),
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  error_message text,
  updated_at timestamptz not null default now()
);

create table training.job_runs (
  id uuid primary key default gen_random_uuid(),
  job_type text not null,
  trigger_source text,
  idempotency_key text,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'partial', 'skipped')),
  started_at timestamptz,
  finished_at timestamptz,
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (finished_at is null or started_at is null or finished_at >= started_at)
);

create unique index job_runs_idempotency_key_uidx
  on training.job_runs (idempotency_key)
  where idempotency_key is not null;
create index job_runs_created_idx
  on training.job_runs (created_at desc);
create index job_runs_status_created_idx
  on training.job_runs (status, created_at desc);

create table training.job_run_stages (
  job_run_id uuid not null references training.job_runs(id) on delete cascade,
  stage_key text not null,
  stage_order smallint not null check (stage_order > 0),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'optional_failed', 'skipped')),
  attempt_count smallint not null default 0 check (attempt_count >= 0),
  started_at timestamptz,
  finished_at timestamptz,
  error_message text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  primary key (job_run_id, stage_key),
  unique (job_run_id, stage_order),
  check (finished_at is null or started_at is null or finished_at >= started_at)
);

-- Maintain updated_at consistently for mutable current-state rows.
create trigger activities_touch_updated_at
before update on training.activities
for each row execute function training.touch_updated_at();

create trigger activity_overrides_touch_updated_at
before update on training.activity_overrides
for each row execute function training.touch_updated_at();

create trigger training_goals_touch_updated_at
before update on training.training_goals
for each row execute function training.touch_updated_at();

create trigger state_documents_touch_updated_at
before update on training.state_documents
for each row execute function training.touch_updated_at();

create trigger mesocycles_touch_updated_at
before update on training.mesocycles
for each row execute function training.touch_updated_at();

create trigger microcycles_touch_updated_at
before update on training.microcycles
for each row execute function training.touch_updated_at();

create trigger planned_workouts_touch_updated_at
before update on training.planned_workouts
for each row execute function training.touch_updated_at();

create trigger integration_sync_state_touch_updated_at
before update on training.integration_sync_state
for each row execute function training.touch_updated_at();

create trigger job_runs_touch_updated_at
before update on training.job_runs
for each row execute function training.touch_updated_at();

-- Phase 1 is server-only. RLS is enabled everywhere and no browser policies exist.
alter table training.activities enable row level security;
alter table training.activity_laps enable row level security;
alter table training.activity_feedback enable row level security;
alter table training.activity_overrides enable row level security;
alter table training.training_goals enable row level security;
alter table training.state_documents enable row level security;
alter table training.mesocycles enable row level security;
alter table training.microcycles enable row level security;
alter table training.planned_workouts enable row level security;
alter table training.planned_workout_revisions enable row level security;
alter table training.coach_evaluations enable row level security;
alter table training.planning_decisions enable row level security;
alter table training.integration_events enable row level security;
alter table training.integration_sync_state enable row level security;
alter table training.job_runs enable row level security;
alter table training.job_run_stages enable row level security;

revoke all on schema training from anon, authenticated;
revoke all on all tables in schema training from anon, authenticated;
revoke all on all sequences in schema training from anon, authenticated;
revoke all on all functions in schema training from anon, authenticated;

grant usage on schema training to service_role;
grant all on all tables in schema training to service_role;
grant all on all sequences in schema training to service_role;
grant execute on all functions in schema training to service_role;
