-- Athlete onboarding/profile persistence for coach planning.
-- The browser never receives table access. Access-protected Worker RPCs are the
-- only write/read surface; server-side planning reads the same relational row.

create table if not exists training.athlete_profiles (
  athlete_subject text primary key,
  schema_version smallint not null default 1,
  status text not null default 'draft',
  current_step smallint not null default 0,
  goals jsonb not null default '[]'::jsonb,
  availability jsonb not null default '{}'::jsonb,
  preferences jsonb not null default '{}'::jsonb,
  constraints jsonb not null default '{}'::jsonb,
  coach_autonomy text not null default 'week_auto',
  preferred_days smallint,
  min_days smallint,
  max_days smallint,
  double_sessions text,
  rest_days text,
  profile jsonb not null,
  revision bigint not null default 1,
  is_planning_default boolean not null default false,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint athlete_profile_subject_format check (athlete_subject ~ '^access:[0-9a-f]{32}$'),
  constraint athlete_profile_schema check (schema_version = 1),
  constraint athlete_profile_status check (status in ('draft', 'complete')),
  constraint athlete_profile_step check (current_step between 0 and 12),
  constraint athlete_profile_goals_json check (jsonb_typeof(goals) = 'array'),
  constraint athlete_profile_availability_json check (jsonb_typeof(availability) = 'object'),
  constraint athlete_profile_preferences_json check (jsonb_typeof(preferences) = 'object'),
  constraint athlete_profile_constraints_json check (jsonb_typeof(constraints) = 'object'),
  constraint athlete_profile_autonomy check (coach_autonomy in ('propose', 'week_auto', 'full_within_constraints')),
  constraint athlete_profile_preferred_days check (preferred_days is null or preferred_days between 1 and 7),
  constraint athlete_profile_min_days check (min_days is null or min_days between 1 and 7),
  constraint athlete_profile_max_days check (max_days is null or max_days between 1 and 7),
  constraint athlete_profile_frequency_order check (
    min_days is null or preferred_days is null or max_days is null
    or (min_days <= preferred_days and preferred_days <= max_days)
  ),
  constraint athlete_profile_double_sessions check (
    double_sessions is null or double_sessions in ('avoid', 'sometimes', 'normal')
  ),
  constraint athlete_profile_rest_days check (
    rest_days is null or rest_days in ('fixed', 'prefer_one', 'load_driven', 'none_required')
  )
);

create unique index if not exists athlete_profiles_one_planning_default_idx
  on training.athlete_profiles (is_planning_default)
  where is_planning_default;

alter table training.athlete_profiles enable row level security;
revoke all on training.athlete_profiles from public, anon, authenticated;

create or replace function public.training_get_athlete_profile(
  p_athlete_subject text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row training.athlete_profiles%rowtype;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;

  select *
  into v_row
  from training.athlete_profiles
  where athlete_subject = p_athlete_subject;

  if not found then
    return jsonb_build_object('status', 'not_found');
  end if;

  return jsonb_build_object(
    'status', 'found',
    'profile', v_row.profile,
    'revision', v_row.revision,
    'updated_at', v_row.updated_at,
    'completed_at', v_row.completed_at
  );
end;
$$;

revoke all on function public.training_get_athlete_profile(text)
  from public, anon, authenticated;
grant execute on function public.training_get_athlete_profile(text) to service_role;

create or replace function public.training_upsert_athlete_profile(
  p_athlete_subject text,
  p_profile jsonb,
  p_set_planning_default boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_schema smallint;
  v_status text;
  v_step smallint;
  v_goals jsonb;
  v_availability jsonb;
  v_preferences jsonb;
  v_constraints jsonb;
  v_frequency jsonb;
  v_preferred smallint;
  v_min smallint;
  v_max smallint;
  v_double text;
  v_rest text;
  v_autonomy text;
  v_revision bigint;
  v_completed timestamptz;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;
  if p_profile is null or jsonb_typeof(p_profile) <> 'object' then
    raise exception 'invalid_profile' using errcode = '22023';
  end if;

  v_schema := coalesce((p_profile->>'schema_version')::smallint, 0);
  v_status := coalesce(p_profile->>'status', '');
  v_step := coalesce((p_profile->>'current_step')::smallint, 0);
  v_goals := coalesce(p_profile->'goals', '[]'::jsonb);
  v_availability := coalesce(p_profile->'availability', '{}'::jsonb);
  v_preferences := coalesce(p_profile->'preferences', '{}'::jsonb);
  v_constraints := coalesce(p_profile->'constraints', '{}'::jsonb);
  v_frequency := coalesce(v_preferences->'frequency', '{}'::jsonb);
  v_autonomy := coalesce(p_profile->>'coach_autonomy', 'week_auto');
  v_double := nullif(v_preferences->>'double_sessions', '');
  v_rest := nullif(v_preferences->>'rest_days', '');

  if v_schema <> 1
     or v_status not in ('draft', 'complete')
     or v_step < 0 or v_step > 12
     or jsonb_typeof(v_goals) <> 'array'
     or jsonb_array_length(v_goals) > 8
     or jsonb_typeof(v_availability) <> 'object'
     or jsonb_typeof(v_preferences) <> 'object'
     or jsonb_typeof(v_constraints) <> 'object'
     or v_autonomy not in ('propose', 'week_auto', 'full_within_constraints')
     or (v_double is not null and v_double not in ('avoid', 'sometimes', 'normal'))
     or (v_rest is not null and v_rest not in ('fixed', 'prefer_one', 'load_driven', 'none_required'))
  then
    raise exception 'invalid_profile_contract' using errcode = '22023';
  end if;

  if v_status = 'complete' and jsonb_array_length(v_goals) < 1 then
    raise exception 'complete_profile_requires_goal' using errcode = '22023';
  end if;

  if v_frequency ? 'preferred_days' then v_preferred := (v_frequency->>'preferred_days')::smallint; end if;
  if v_frequency ? 'min_days' then v_min := (v_frequency->>'min_days')::smallint; end if;
  if v_frequency ? 'max_days' then v_max := (v_frequency->>'max_days')::smallint; end if;

  if v_status = 'complete' and (
    v_preferred is null or v_min is null or v_max is null
    or v_min < 1 or v_max > 7 or v_min > v_preferred or v_preferred > v_max
  ) then
    raise exception 'invalid_training_frequency' using errcode = '22023';
  end if;

  if p_set_planning_default and v_status = 'complete' then
    update training.athlete_profiles set is_planning_default = false where is_planning_default;
  end if;

  v_completed := case when v_status = 'complete' then now() else null end;

  insert into training.athlete_profiles (
    athlete_subject, schema_version, status, current_step, goals, availability,
    preferences, constraints, coach_autonomy, preferred_days, min_days, max_days,
    double_sessions, rest_days, profile, revision, is_planning_default,
    completed_at, updated_at
  )
  values (
    p_athlete_subject, v_schema, v_status, v_step, v_goals, v_availability,
    v_preferences, v_constraints, v_autonomy, v_preferred, v_min, v_max,
    v_double, v_rest, p_profile, 1,
    (p_set_planning_default and v_status = 'complete'), v_completed, now()
  )
  on conflict (athlete_subject) do update set
    schema_version = excluded.schema_version,
    status = excluded.status,
    current_step = excluded.current_step,
    goals = excluded.goals,
    availability = excluded.availability,
    preferences = excluded.preferences,
    constraints = excluded.constraints,
    coach_autonomy = excluded.coach_autonomy,
    preferred_days = excluded.preferred_days,
    min_days = excluded.min_days,
    max_days = excluded.max_days,
    double_sessions = excluded.double_sessions,
    rest_days = excluded.rest_days,
    profile = excluded.profile,
    revision = training.athlete_profiles.revision + 1,
    is_planning_default = case
      when p_set_planning_default and v_status = 'complete' then true
      else training.athlete_profiles.is_planning_default
    end,
    completed_at = case
      when v_status = 'complete' then coalesce(training.athlete_profiles.completed_at, now())
      else training.athlete_profiles.completed_at
    end,
    updated_at = now()
  returning revision, completed_at into v_revision, v_completed;

  return jsonb_build_object(
    'status', 'saved',
    'revision', v_revision,
    'profile_status', v_status,
    'planning_default', (p_set_planning_default and v_status = 'complete'),
    'completed_at', v_completed
  );
end;
$$;

revoke all on function public.training_upsert_athlete_profile(text, jsonb, boolean)
  from public, anon, authenticated;
grant execute on function public.training_upsert_athlete_profile(text, jsonb, boolean) to service_role;

comment on table training.athlete_profiles is
  'Per-athlete declared goals, hard life constraints and training preferences. Observed capacity remains in athlete_state and is not stored here.';
comment on column training.athlete_profiles.is_planning_default is
  'Single-athlete bridge for the current hall-training runtime. Future multi-user workers should select by athlete_subject instead of relying on this flag.';
