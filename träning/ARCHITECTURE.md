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

## Legacy renderer containment

The current renderer still contains 53 ordered mutation/validation stages.
That is legacy debt, not the target architecture. Until it is replaced by a
single view-model renderer, it runs only inside `render_transaction.py`.

Migration rule: move one coherent surface at a time from post-render mutation
into source rendering, add a domain regression test, then delete the redundant
finalizer. Never add a new HTML finalizer.

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
