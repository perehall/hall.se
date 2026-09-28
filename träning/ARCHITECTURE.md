# Training system reliability contract

## Target flow

```
Providers -> ingest/normalize -> canonical activity state (Supabase)
                           -> planning/coach runtime state (Supabase)
                           -> publication transaction -> validated static site
```

Canonical state and publication are separate failure domains. A presentation
failure must never invalidate an already accepted activity, plan, or coach
state.

## Invariants

1. **Supabase is canonical runtime state.** Repository JSON is a materialized
   working representation and must not be treated as a second authoritative
   database.
2. **Ingest is durable before presentation.** Activity promotion and final
   runtime-state commit happen before publication.
3. **Publication is atomic.** Rendering either completes and validates, or the
   complete pre-render training tree is restored.
4. **Last known good UI wins.** A renderer defect degrades publication; it does
   not replace the current site with a partial build.
5. **Deterministic failures are not retried.** Retries are reserved for
   explicitly identified remote/enrichment stages.
6. **Current-date tests must express domain truth, not incidental markup.**
   Optional UI such as a "next workout" row cannot be required on dates where
   no next planned day exists.
7. **Actual activity truth outranks prescription.** Once one or more canonical
   activities exist for a date, the primary Today surface describes those
   activities rather than claiming the planned prescription was completed.
8. **Calendar dates are containers, not workout identities.** A date may hold
   zero, one or many independent planned workouts. Each physical workout has its
   own identity and prescription.
9. **Do not encode co-location as a composite recipe.** Swim + strength, run +
   bike or any other same-day combination remains separate workouts. A single
   workout may contain multiple sports only when it is explicitly a multisport
   session with ordered components, such as a brick.
10. **Runtime migration never guesses physical workout structure.** Premultipass
    documents must be migrated explicitly offline. Production code may project
    canonical workouts into a compatibility calendar cache, but it may not
    split, merge or infer workouts from that cache.

## Legacy renderer containment

Production uses the pure v2 renderer. The old ordered mutation/finalizer chain
is retained only as parity/history debt and must not regain production
ownership.

Migration rule: move or delete one coherent legacy capability at a time, keep a
domain regression test, and never add a new HTML finalizer or a new
sport/date-specific compatibility path.

## Required end-to-end contracts

- New run/swim/bike/MTB/enduro activity -> normalized canonical type -> visible
  as the actual completed session for that date.
- Multiple activities on one day -> all visible; no planned session presented
  as completed instead.
- Manual activity edit -> canonical state changes once -> next publication
  reflects the edit.
- Rest day with no activity -> remains rest day.
- Publication failure -> canonical state remains committed -> previous site
  remains intact.
- Unknown provider activity type -> safe public fallback; no raw provider value
  can crash publication.

## Change policy

Training changes go through a branch and PR. Required regression suites must be
green before merge. Production workflows should not be used as an interactive
debugger.
