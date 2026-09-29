-- Durable, per-athlete plan generation requests.
-- A completed athlete profile is a prerequisite. Browser access remains behind
-- the Access-protected Worker; only service_role may execute these RPCs.

create table if not exists training.plan_generation_requests (
  id uuid primary key default gen_random_uuid(),
  athlete_subject text not null references training.athlete_profiles(athlete_subject) on delete cascade,
  profile_revision bigint not null,
  status text not null default 'queued',
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  error text,
  result_week_key text,
  constraint plan_generation_status check (status in ('queued','running','completed','failed'))
);

create index if not exists plan_generation_requests_athlete_idx
  on training.plan_generation_requests (athlete_subject, requested_at desc);

create unique index if not exists plan_generation_requests_one_active_per_athlete_idx
  on training.plan_generation_requests (athlete_subject)
  where status in ('queued','running');

alter table training.plan_generation_requests enable row level security;
revoke all on training.plan_generation_requests from public, anon, authenticated;

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
  v_request training.plan_generation_requests%rowtype;
  v_created boolean := false;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;

  select *
  into v_profile
  from training.athlete_profiles
  where athlete_subject = p_athlete_subject
    and status = 'complete';

  if not found then
    raise exception 'complete_profile_required' using errcode = '22023';
  end if;

  select *
  into v_request
  from training.plan_generation_requests
  where athlete_subject = p_athlete_subject
    and status in ('queued','running')
  order by requested_at desc
  limit 1;

  if not found then
    insert into training.plan_generation_requests (
      athlete_subject, profile_revision, status
    )
    values (
      p_athlete_subject, v_profile.revision, 'queued'
    )
    returning * into v_request;
    v_created := true;
  end if;

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'profile_revision', v_request.profile_revision,
    'created', v_created,
    'requested_at', v_request.requested_at,
    'updated_at', v_request.updated_at
  );
end;
$$;

revoke all on function public.training_request_plan_generation(text)
  from public, anon, authenticated;
grant execute on function public.training_request_plan_generation(text) to service_role;

create or replace function public.training_get_plan_generation(
  p_athlete_subject text,
  p_request_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request training.plan_generation_requests%rowtype;
begin
  if p_athlete_subject is null or p_athlete_subject !~ '^access:[0-9a-f]{32}$' then
    raise exception 'invalid_athlete_subject' using errcode = '22023';
  end if;

  select *
  into v_request
  from training.plan_generation_requests
  where id = p_request_id
    and athlete_subject = p_athlete_subject;

  if not found then
    return jsonb_build_object('status', 'not_found');
  end if;

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'profile_revision', v_request.profile_revision,
    'requested_at', v_request.requested_at,
    'started_at', v_request.started_at,
    'completed_at', v_request.completed_at,
    'updated_at', v_request.updated_at,
    'result_week_key', v_request.result_week_key,
    'error', v_request.error
  );
end;
$$;

revoke all on function public.training_get_plan_generation(text, uuid)
  from public, anon, authenticated;
grant execute on function public.training_get_plan_generation(text, uuid) to service_role;

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
    started_at = case
      when p_status = 'running' then coalesce(started_at, now())
      else started_at
    end,
    completed_at = case
      when p_status in ('completed','failed') then now()
      else completed_at
    end,
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

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'updated_at', v_request.updated_at,
    'result_week_key', v_request.result_week_key
  );
end;
$$;

revoke all on function public.training_set_plan_generation_status(uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.training_set_plan_generation_status(uuid, text, text, text) to service_role;

comment on table training.plan_generation_requests is
  'Durable user-initiated plan builds. Profile revision is snapshotted when generation is requested.';
