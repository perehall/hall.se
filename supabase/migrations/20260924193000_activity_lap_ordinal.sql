-- Preserve every recorded lap even when historical source lap_index values
-- are duplicated or otherwise unsuitable as relational identity.
--
-- lap_ordinal is the stable list position inside the canonical activity
-- document. lap_index remains source data and may legitimately duplicate.

alter table training.activity_laps
  add column if not exists lap_ordinal integer;

update training.activity_laps
set lap_ordinal = lap_index
where lap_ordinal is null;

alter table training.activity_laps
  alter column lap_ordinal set not null;

alter table training.activity_laps
  drop constraint if exists activity_laps_pkey;

alter table training.activity_laps
  add primary key (activity_id, lap_ordinal);

create index if not exists activity_laps_source_index_idx
  on training.activity_laps (activity_id, lap_index);

comment on column training.activity_laps.lap_ordinal is
  'Canonical list position used as relational identity. Unlike source lap_index it must be unique within the activity.';
