-- Direct, durable training feedback write path.
-- The browser still talks only to the Access-protected Cloudflare Worker.
-- The Worker calls this RPC with a backend-only Supabase secret key.
-- The RPC is intentionally narrow: append one validated feedback event for one
-- existing Strava activity. It does not expose training tables to browser roles.

create or replace function public.training_submit_activity_feedback(
  p_provider_activity_id text,
  p_source text,
  p_operation text,
  p_feedback_text text,
  p_rpe smallint,
  p_feeling text[],
  p_event_key text,
  p_submitted_at timestamptz,
  p_raw jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_activity_id uuid;
  v_feedback_id uuid;
  v_allowed_operations constant text[] := array[
    'ADD_FEEDBACK',
    'UPDATE_COMPLETED_WORKOUT',
    'ADD_SPONTANEOUS_WORKOUT',
    'REPORT_PAIN',
    'REPORT_FATIGUE',
    'NATURAL_LANGUAGE'
  ];
  v_allowed_feelings constant text[] := array[
    'fresh',
    'tired',
    'strong_legs',
    'heavy_legs',
    'pain',
    'could_do_more'
  ];
begin
  if p_provider_activity_id is null
     or btrim(p_provider_activity_id) = ''
     or p_provider_activity_id !~ '^[0-9]+$' then
    raise exception 'invalid_activity_id' using errcode = '22023';
  end if;

  if p_source is null or btrim(p_source) = '' or length(p_source) > 64 then
    raise exception 'invalid_source' using errcode = '22023';
  end if;

  if p_operation is null or not (p_operation = any(v_allowed_operations)) then
    raise exception 'invalid_operation' using errcode = '22023';
  end if;

  if p_feedback_text is not null and length(p_feedback_text) > 800 then
    raise exception 'invalid_feedback_text' using errcode = '22023';
  end if;

  if p_rpe is not null and (p_rpe < 1 or p_rpe > 10) then
    raise exception 'invalid_rpe' using errcode = '22023';
  end if;

  if coalesce(cardinality(p_feeling), 0) > 6
     or exists (
       select 1
       from unnest(coalesce(p_feeling, '{}'::text[])) as feeling(value)
       where not (value = any(v_allowed_feelings))
     ) then
    raise exception 'invalid_feeling' using errcode = '22023';
  end if;

  if coalesce(btrim(p_feedback_text), '') = ''
     and p_rpe is null
     and coalesce(cardinality(p_feeling), 0) = 0 then
    raise exception 'empty_input' using errcode = '22023';
  end if;

  if p_event_key is null
     or p_event_key !~ '^training-input:[0-9a-f]{24}$' then
    raise exception 'invalid_event_key' using errcode = '22023';
  end if;

  if p_raw is null or jsonb_typeof(p_raw) <> 'object' then
    raise exception 'invalid_raw_payload' using errcode = '22023';
  end if;

  select a.id
    into v_activity_id
  from training.activities as a
  where a.provider = 'strava'
    and a.provider_activity_id = p_provider_activity_id
    and a.is_current
  limit 1;

  if v_activity_id is null then
    raise exception 'activity_not_found' using errcode = 'P0002';
  end if;

  insert into training.activity_feedback (
    activity_id,
    source,
    operation,
    feedback_text,
    rpe,
    feeling,
    event_key,
    submitted_at,
    raw
  )
  values (
    v_activity_id,
    btrim(p_source),
    p_operation,
    nullif(btrim(coalesce(p_feedback_text, '')), ''),
    p_rpe,
    coalesce(p_feeling, '{}'::text[]),
    p_event_key,
    coalesce(p_submitted_at, now()),
    p_raw
  )
  on conflict (event_key) where event_key is not null
  do nothing
  returning id into v_feedback_id;

  if v_feedback_id is null then
    select f.id
      into v_feedback_id
    from training.activity_feedback as f
    where f.event_key = p_event_key;
  end if;

  insert into training.integration_events (
    provider,
    event_key,
    event_type,
    status,
    payload
  )
  values (
    'training_gui',
    p_event_key,
    p_operation,
    'received',
    p_raw
  )
  on conflict (provider, event_key) do nothing;

  return jsonb_build_object(
    'status', 'saved',
    'event_key', p_event_key,
    'feedback_id', v_feedback_id
  );
end;
$$;

comment on function public.training_submit_activity_feedback(
  text, text, text, text, smallint, text[], text, timestamptz, jsonb
) is
  'Backend-only RPC used by the Access-protected Worker to durably append one training feedback event before asynchronous coaching/planning.';

revoke all on function public.training_submit_activity_feedback(
  text, text, text, text, smallint, text[], text, timestamptz, jsonb
) from public, anon, authenticated;

grant execute on function public.training_submit_activity_feedback(
  text, text, text, text, smallint, text[], text, timestamptz, jsonb
) to service_role;
