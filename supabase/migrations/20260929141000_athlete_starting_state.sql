-- Per-athlete starting-state onboarding and immutable generation snapshots.
-- Declared starting level is separate from preferences and from observed athlete_state.
-- Observed training history may be offered as a candidate only for the current
-- single-athlete runtime; multi-user subjects without an attributed activity
-- history fall back to explicit manual onboarding rather than inference.

create table if not exists training.athlete_starting_states (
  athlete_subject text primary key references training.athlete_profiles(athlete_subject) on delete cascade,
  schema_version smallint not null default 1,
  status text not null default 'draft',
  source_mode text not null default 'manual',
  manual_state jsonb not null default '{}'::jsonb,
  observed_snapshot jsonb,
  confirmation jsonb not null default '{}'::jsonb,
  state jsonb not null,
  revision bigint not null default 1,
  active_state jsonb,
  active_revision bigint,
  activated_at timestamptz,
  confirmed_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint athlete_starting_state_schema check (schema_version = 1),
  constraint athlete_starting_state_status check (status in ('draft','confirmed')),
  constraint athlete_starting_state_source_mode check (source_mode in ('observed','manual','hybrid')),
  constraint athlete_starting_state_manual_json check (jsonb_typeof(manual_state) = 'object'),
  constraint athlete_starting_state_observed_json check (
    observed_snapshot is null or jsonb_typeof(observed_snapshot) = 'object'
  ),
  constraint athlete_starting_state_confirmation_json check (jsonb_typeof(confirmation) = 'object'),
  constraint athlete_starting_state_state_json check (jsonb_typeof(state) = 'object'),
  constraint athlete_starting_state_active_json check (
    active_state is null or jsonb_typeof(active_state) = 'object'
  )
);

alter table training.athlete_starting_states enable row level security;
revoke all on training.athlete_starting_states from public, anon, authenticated;

create or replace function training.current_observed_starting_candidate(
  p_athlete_subject text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_is_default boolean := false;
  v_state jsonb;
  v_recent jsonb;
  v_count integer := 0;
begin
  select coalesce(is_planning_default, false)
  into v_is_default
  from training.athlete_profiles
  where athlete_subject = p_athlete_subject;

  if not coalesce(v_is_default, false) then
    return null;
  end if;

  select payload
  into v_state
  from training.state_documents
  where document_key = 'athlete_state';

  if not found or v_state is null then
    return null;
  end if;

  v_recent := coalesce(v_state->'load_windows'->'windows'->'recent_28d', '{}'::jsonb);
  v_count := coalesce((v_recent->>'activity_count')::integer, 0);

  -- Four recent activities is merely a presentation threshold for offering
  -- history to the athlete for confirmation. It is not a physiological
  -- sufficiency claim and never authorizes progression.
  if v_count < 4 then
    return null;
  end if;

  return jsonb_build_object(
    'schema_version', 1,
    'source', 'observed_training_history',
    'as_of', v_state->'fact_window'->>'end',
    'fact_window', v_state->'fact_window',
    'recent_28d', v_recent,
    'by_family', coalesce(v_state->'by_family', '{}'::jsonb),
    'capability_facts', coalesce(v_state->'capability_facts', '{}'::jsonb),
    'dose_response', coalesce(v_state->'dose_response'->'by_capability', '{}'::jsonb),
    'interpretation_boundary',
      'Observerade träningsfakta för bekräftelse. Historik är inte bevis för optimal belastning eller framtida progression.'
  );
end;
$$;

revoke all on function training.current_observed_starting_candidate(text)
  from public, anon, authenticated;
grant execute on function training.current_observed_starting_candidate(text) to service_role;

create or replace function public.training_get_athlete_starting_state(
  p_athlete_subject text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row training.athlete_starting_states%rowtype;
  v_candidate jsonb;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;

  v_candidate := training.current_observed_starting_candidate(p_athlete_subject);

  select *
  into v_row
  from training.athlete_starting_states
  where athlete_subject = p_athlete_subject;

  if not found then
    return jsonb_build_object(
      'status', 'not_found',
      'observed_candidate', v_candidate
    );
  end if;

  return jsonb_build_object(
    'status', 'found',
    'starting_state', v_row.state,
    'revision', v_row.revision,
    'updated_at', v_row.updated_at,
    'confirmed_at', v_row.confirmed_at,
    'observed_candidate', v_candidate
  );
end;
$$;

revoke all on function public.training_get_athlete_starting_state(text)
  from public, anon, authenticated;
grant execute on function public.training_get_athlete_starting_state(text) to service_role;

create or replace function public.training_upsert_athlete_starting_state(
  p_athlete_subject text,
  p_state jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_schema smallint;
  v_status text;
  v_source_mode text;
  v_manual jsonb;
  v_confirmation jsonb;
  v_observed jsonb;
  v_stored jsonb;
  v_revision bigint;
  v_confirmed timestamptz;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;
  if p_state is null or jsonb_typeof(p_state) <> 'object' then
    raise exception 'invalid_starting_state' using errcode = '22023';
  end if;

  v_schema := coalesce((p_state->>'schema_version')::smallint, 0);
  v_status := coalesce(p_state->>'status', '');
  v_source_mode := coalesce(p_state->>'source_mode', '');
  v_manual := coalesce(p_state->'manual_state', '{}'::jsonb);
  v_confirmation := coalesce(p_state->'confirmation', '{}'::jsonb);

  if v_schema <> 1
     or v_status not in ('draft','confirmed')
     or v_source_mode not in ('observed','manual','hybrid')
     or jsonb_typeof(v_manual) <> 'object'
     or jsonb_typeof(v_confirmation) <> 'object'
  then
    raise exception 'invalid_starting_state_contract' using errcode = '22023';
  end if;

  if v_source_mode in ('observed','hybrid') then
    v_observed := training.current_observed_starting_candidate(p_athlete_subject);
  else
    v_observed := null;
  end if;

  if v_status = 'confirmed' then
    if v_source_mode = 'observed' and v_observed is null then
      raise exception 'observed_starting_state_unavailable' using errcode = '22023';
    end if;
    if v_source_mode = 'observed'
       and coalesce((v_confirmation->>'observed_representative')::boolean, false) is not true
    then
      raise exception 'observed_starting_state_requires_confirmation' using errcode = '22023';
    end if;
    if v_source_mode = 'manual' and v_manual = '{}'::jsonb then
      raise exception 'manual_starting_state_required' using errcode = '22023';
    end if;
  end if;

  v_stored := jsonb_build_object(
    'schema_version', 1,
    'status', v_status,
    'source_mode', v_source_mode,
    'observed_snapshot', v_observed,
    'manual_state', v_manual,
    'confirmation', v_confirmation
  );

  insert into training.athlete_starting_states (
    athlete_subject, schema_version, status, source_mode, manual_state,
    observed_snapshot, confirmation, state, revision, confirmed_at, updated_at
  )
  values (
    p_athlete_subject, 1, v_status, v_source_mode, v_manual,
    v_observed, v_confirmation, v_stored, 1,
    case when v_status = 'confirmed' then now() else null end,
    now()
  )
  on conflict (athlete_subject) do update set
    schema_version = excluded.schema_version,
    status = excluded.status,
    source_mode = excluded.source_mode,
    manual_state = excluded.manual_state,
    observed_snapshot = excluded.observed_snapshot,
    confirmation = excluded.confirmation,
    state = excluded.state,
    revision = training.athlete_starting_states.revision + 1,
    confirmed_at = case
      when v_status = 'confirmed' then now()
      else training.athlete_starting_states.confirmed_at
    end,
    updated_at = now()
  returning revision, confirmed_at into v_revision, v_confirmed;

  return jsonb_build_object(
    'status', 'saved',
    'revision', v_revision,
    'starting_state_status', v_status,
    'source_mode', v_source_mode,
    'confirmed_at', v_confirmed
  );
end;
$$;

revoke all on function public.training_upsert_athlete_starting_state(text, jsonb)
  from public, anon, authenticated;
grant execute on function public.training_upsert_athlete_starting_state(text, jsonb) to service_role;

alter table training.plan_generation_requests
  add column if not exists starting_state_revision bigint,
  add column if not exists starting_state_snapshot jsonb;

alter table training.plan_generation_requests
  drop constraint if exists plan_generation_starting_state_snapshot_json;

alter table training.plan_generation_requests
  add constraint plan_generation_starting_state_snapshot_json check (
    starting_state_snapshot is null or jsonb_typeof(starting_state_snapshot) = 'object'
  );

create or replace function public.training_request_plan_generation(
  p_athlete_subject text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile training.athlete_profiles%rowtype;
  v_start training.athlete_starting_states%rowtype;
  v_request training.plan_generation_requests%rowtype;
  v_created boolean := false;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;

  select * into v_profile
  from training.athlete_profiles
  where athlete_subject = p_athlete_subject
    and status = 'complete';
  if not found then
    raise exception 'complete_profile_required' using errcode = '22023';
  end if;

  select * into v_start
  from training.athlete_starting_states
  where athlete_subject = p_athlete_subject
    and status = 'confirmed';
  if not found then
    raise exception 'confirmed_starting_state_required' using errcode = '22023';
  end if;

  select * into v_request
  from training.plan_generation_requests
  where athlete_subject = p_athlete_subject
    and status in ('queued','running')
  order by requested_at desc
  limit 1;

  if not found then
    insert into training.plan_generation_requests (
      athlete_subject, profile_revision, profile_snapshot,
      starting_state_revision, starting_state_snapshot, status
    )
    values (
      p_athlete_subject, v_profile.revision, v_profile.profile,
      v_start.revision, v_start.state, 'queued'
    )
    returning * into v_request;
    v_created := true;
  end if;

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'profile_revision', v_request.profile_revision,
    'starting_state_revision', v_request.starting_state_revision,
    'created', v_created,
    'requested_at', v_request.requested_at,
    'updated_at', v_request.updated_at
  );
end;
$$;

revoke all on function public.training_request_plan_generation(text)
  from public, anon, authenticated;
grant execute on function public.training_request_plan_generation(text) to service_role;

create or replace function public.training_set_plan_generation_status(
  p_request_id uuid,
  p_status text,
  p_error text default null,
  p_result_week_key text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request training.plan_generation_requests%rowtype;
begin
  if p_status not in ('queued','running','completed','failed') then
    raise exception 'invalid_generation_status' using errcode = '22023';
  end if;

  update training.plan_generation_requests
  set
    status = p_status,
    started_at = case when p_status = 'running' then coalesce(started_at, now()) else started_at end,
    completed_at = case when p_status in ('completed','failed') then now() else completed_at end,
    error = case
      when p_status = 'failed' then left(coalesce(p_error, 'generation_failed'), 1200)
      when p_status in ('queued','running','completed') then null
      else error
    end,
    result_week_key = coalesce(p_result_week_key, result_week_key),
    updated_at = now()
  where id = p_request_id
  returning * into v_request;

  if not found then
    raise exception 'generation_request_not_found' using errcode = '22023';
  end if;

  if p_status = 'completed' then
    update training.athlete_profiles
    set
      active_profile = v_request.profile_snapshot,
      active_revision = v_request.profile_revision,
      activated_at = now()
    where athlete_subject = v_request.athlete_subject;

    update training.athlete_starting_states
    set
      active_state = v_request.starting_state_snapshot,
      active_revision = v_request.starting_state_revision,
      activated_at = now()
    where athlete_subject = v_request.athlete_subject;
  end if;

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'updated_at', v_request.updated_at,
    'result_week_key', v_request.result_week_key,
    'active_profile_revision', case when p_status = 'completed' then v_request.profile_revision else null end,
    'active_starting_state_revision', case when p_status = 'completed' then v_request.starting_state_revision else null end
  );
end;
$$;

revoke all on function public.training_set_plan_generation_status(uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.training_set_plan_generation_status(uuid, text, text, text) to service_role;

comment on table training.athlete_starting_states is
  'Per-athlete onboarding baseline. User-confirmed starting level is distinct from preferences and from continuously observed athlete_state.';
