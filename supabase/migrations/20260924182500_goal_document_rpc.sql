-- First promoted functional read: planner goal portfolio.
-- The goal is already published on hall.se/träning/malbild; this RPC exposes
-- only that same document through a narrow read-only function. No training
-- tables or schema privileges are granted to browser roles.

create or replace function public.training_goal_document()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
select jsonb_build_object(
  'status', 'ok',
  'source', 'supabase',
  'source_hash', d.source_hash,
  'updated_at', d.updated_at,
  'payload', d.payload
)
from training.state_documents d
where d.document_key = 'goal'
limit 1;
$$;

revoke all on function public.training_goal_document() from public;
grant execute on function public.training_goal_document() to anon, authenticated;

comment on function public.training_goal_document() is
  'Read-only promoted goal-document surface. Returns the same training goal portfolio already published on the public training goal page; grants no table access.';
