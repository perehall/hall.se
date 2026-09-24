-- Promote activity state to a current relational runtime source.
-- Historical activity rows are retained, while is_current marks the exact
-- Strava snapshot allowed to feed athlete-state/planning.

alter table training.activities
  add column if not exists is_current boolean not null default true;

alter table training.activities
  add column if not exists last_seen_source_hash text;

update training.activities
set is_current = true
where is_current is distinct from true;

create index if not exists activities_current_started_idx
  on training.activities (started_at desc)
  where is_current;

comment on column training.activities.is_current is
  'True only when the activity belongs to the latest promoted Strava snapshot. Historical rows are retained with false.';

comment on column training.activities.last_seen_source_hash is
  'Hash of the promoted activity+override snapshot that most recently marked this activity current.';
