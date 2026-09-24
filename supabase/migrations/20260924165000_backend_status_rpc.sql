-- Public, read-only backend health RPC.
-- This is intentionally the only browser-readable surface introduced in this phase.
-- No training tables or custom schemas are exposed to anon/authenticated.

create or replace function public.training_backend_status()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
with latest as (
  select
    status,
    updated_at,
    metadata
  from training.job_runs
  where job_type = 'supabase_shadow_import'
    and status = 'succeeded'
  order by updated_at desc
  limit 1
),
facts as (
  select
    (select count(*)::integer
       from training.planned_workouts
      where is_current) as current_workouts,
    (select count(*)::integer
       from training.state_documents) as state_documents
)
select jsonb_build_object(
  'status',
    case
      when latest.status = 'succeeded'
       and facts.current_workouts = coalesce((latest.metadata #>> '{counts,planned_workouts}')::integer, -1)
       and facts.state_documents = coalesce((latest.metadata #>> '{counts,state_documents}')::integer, -1)
      then 'ok'
      else 'degraded'
    end,
  'source', 'supabase',
  'last_sync_at', latest.updated_at,
  'snapshot', left(coalesce(latest.metadata ->> 'source_hash', ''), 12),
  'current_workouts', facts.current_workouts,
  'expected_current_workouts', coalesce((latest.metadata #>> '{counts,planned_workouts}')::integer, 0),
  'state_documents', facts.state_documents,
  'expected_state_documents', coalesce((latest.metadata #>> '{counts,state_documents}')::integer, 0)
)
from facts
left join latest on true;
$$;

revoke all on function public.training_backend_status() from public;
grant execute on function public.training_backend_status() to anon, authenticated;

comment on function public.training_backend_status() is
  'Sanitized browser-readable health probe for the hall-training Supabase shadow backend. Exposes no training content.';
