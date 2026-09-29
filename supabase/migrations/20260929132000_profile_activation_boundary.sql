-- Separate "profile saved" from "profile activated for planning".
-- A generation request freezes the exact profile revision it was created from.
-- Only a successfully completed canonical generation promotes that snapshot to
-- the athlete's active planning profile.

alter table training.athlete_profiles
  add column if not exists active_profile jsonb,
  add column if not exists active_revision bigint,
  add column if not exists activated_at timestamptz;

alter table training.athlete_profiles
  drop constraint if exists athlete_profile_active_profile_json;

alter table training.athlete_profiles
  add constraint athlete_profile_active_profile_json check (
    active_profile is null or jsonb_typeof(active_profile) = 'object'
  );

alter table training.plan_generation_requests
  add column if not exists profile_snapshot jsonb;

update training.plan_generation_requests r
set profile_snapshot = p.profile
from training.athlete_profiles p
where r.athlete_subject = p.athlete_subject
  and r.profile_snapshot is null;

alter table training.plan_generation_requests
  alter column profile_snapshot set not null;

alter table training.plan_generation_requests
  drop constraint if exists plan_generation_profile_snapshot_json;

alter table training.plan_generation_requests
  add constraint plan_generation_profile_snapshot_json check (
    jsonb_typeof(profile_snapshot) = 'object'
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
      athlete_subject, profile_revision, profile_snapshot, status
    )
    values (
      p_athlete_subject, v_profile.revision, v_profile.profile, 'queued'
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

  if p_status = 'completed' then
    update training.athlete_profiles
    set
      active_profile = v_request.profile_snapshot,
      active_revision = v_request.profile_revision,
      activated_at = now()
    where athlete_subject = v_request.athlete_subject;
  end if;

  return jsonb_build_object(
    'status', v_request.status,
    'request_id', v_request.id,
    'updated_at', v_request.updated_at,
    'result_week_key', v_request.result_week_key,
    'active_profile_revision', case
      when p_status = 'completed' then v_request.profile_revision
      else null
    end
  );
end;
$$;

revoke all on function public.training_set_plan_generation_status(uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.training_set_plan_generation_status(uuid, text, text, text) to service_role;

comment on column training.athlete_profiles.active_profile is
  'Exact athlete profile snapshot last promoted by a successfully completed canonical plan generation.';
comment on column training.athlete_profiles.active_revision is
  'Revision of active_profile. Saving or editing a profile does not change this value.';
comment on column training.plan_generation_requests.profile_snapshot is
  'Immutable profile snapshot used by this request; prevents later edits or other athletes from changing an in-flight build.';
