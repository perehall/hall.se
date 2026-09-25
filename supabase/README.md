# Training backend (Supabase)

This directory contains the version-controlled database contract for the training system.

## Migration status

Supabase started in **shadow mode**. The migration has now promoted selected production domains to required runtime authority while retaining the original shadow/reconciliation layer for remaining domains and audit.

- Activities/feedback, athlete-state, planning state and coach state use verified Supabase runtime commit/readback paths.
- JSON files for promoted domains are compatibility caches/audit artifacts after successful database readback.
- The existing static GitHub Pages renderer remains in place and consumes those verified compatibility caches.
- No direct browser access to private training tables is granted; only explicitly defined sanitized RPCs are exposed.

The first schema separates stable domain entities (activities, feedback, plans, goals and job history) from fast-changing generated documents. Generated/derived documents can initially be mirrored in `training.state_documents` as JSONB while their long-term relational model is validated.

## Security

All tables live in the `training` schema.

Row Level Security is enabled on every table. The initial migration defines **no policies for `anon` or `authenticated`**, so the browser cannot access training data. Backend access will be introduced explicitly in a later migration.

Do not commit Supabase keys, database passwords or access tokens.

## Deployment

The Supabase GitHub integration watches `supabase/migrations/`. With production deployment enabled, pending migrations merged to the configured production branch are applied to the `hall-training` project.

Promoted production domains now depend on this database during update execution. A runtime database failure fails the new update closed before publication; the previously published site remains intact.

## Next migration step

After this schema is deployed:

1. add a one-way importer from the canonical JSON files;
2. import into shadow tables using idempotent upserts;
3. compare source counts/keys and selected records;
4. run the shadow path for several updates;
5. only then promote individual entities to database source-of-truth.


## Manual shadow import

Database writes are intentionally not part of the normal training pipeline yet.

The workflow `.github/workflows/supabase-shadow-import.yml` is manual-only and has two modes:

- `check` validates the database connection, schema contract and deterministic source payload without writing rows.
- `write` performs the full shadow import in one PostgreSQL transaction, verifies the imported natural keys and document hashes, and commits only after verification succeeds.

The workflow reads the database connection only from the GitHub Actions secret `SUPABASE_DB_URL`. It never prints that value.

A successful `write` records an idempotent `supabase_shadow_import` job in `training.job_runs`, keyed by the canonical source hash. Re-running the same source snapshot must not create duplicate domain rows.


## Automatic shadow sync

After the manual import and repeated-write idempotency checks succeeded, the normal training workflow mirrors canonical state to Supabase after the critical update job has completed successfully.

The automatic shadow sync is deliberately a separate non-blocking job:

- it depends on the canonical `update` job succeeding;
- it checks out current `main` after the writer has finished, so it mirrors the canonical committed snapshot rather than an in-memory intermediate state;
- it retries transient failures up to three times;
- `continue-on-error: true` prevents a Supabase outage or importer defect from failing the canonical training workflow or blocking site publication;
- a later scheduled/webhook/manual training run retries the complete idempotent shadow write, making the mirror self-healing.

Supabase remains secondary during this phase. The frontend, planner, Strava ingest and coach do not read from it yet.


## Independent read-back canary

Before any live consumer is allowed to read from Supabase, every automatic shadow write is followed by a second process that opens a fresh PostgreSQL connection and sets the transaction read-only.

The canary verifies:

- the committed source hash and count manifest for the current canonical snapshot;
- exact natural-key sets for mutable current-state entities and presence of all canonical keys in append-retained history entities;
- every persisted `state_documents.payload` by recomputing its canonical hash from the database value.

This catches missing rows, stale/extra rows and persisted document drift that an in-transaction writer verification alone cannot prove.

The manual `Supabase shadow import` workflow therefore exposes three modes:

- `check`: connection and schema only, no write;
- `write`: transactional write followed by independent read-back;
- `audit`: read-only comparison of the already persisted shadow against current canonical JSON.

A canary failure remains non-blocking for the canonical training update. Supabase is still not a source of truth and no planner, coach or frontend reads from it.


## Current plan versus retained history

The first read-back canary exposed an important distinction: replanning can change a future workout key, so simple upserts leave older plan rows behind.

`training.planned_workouts` therefore carries explicit snapshot currentness:

- `is_current = true` identifies only workouts in the latest canonical plan snapshot;
- `last_seen_source_hash` records the canonical snapshot that last activated the row;
- each shadow write clears previous current flags and activates the new set in the same transaction;
- older workout rows are retained for history instead of being destructively deleted.

The read-back canary requires an exact match for the current planned-workout set. Historical entities such as activities, feedback and coach evaluations are append-retained; for them the canary requires all canonical rows to be present but permits older database history.


## First live consumer: backend status

The first production read path is deliberately non-critical. The training site's system-info dialog can call a single sanitized RPC, `public.training_backend_status()`, using the project's browser-safe publishable key.

Security boundaries:

- no table in the `training` schema is granted to `anon` or `authenticated`;
- the RPC is `SECURITY DEFINER` with an empty `search_path` and uses fully qualified table names;
- only `EXECUTE` on this one function is granted to browser roles;
- the response contains technical health metadata only: status, last shadow write time, short snapshot id and structural counts;
- database passwords, secret/service-role keys and training content never enter browser HTML.

The UI hides the backend row when `SUPABASE_PUBLISHABLE_KEY` is absent. The browser status RPC is optional; server-side goal and activity runtime reads use the database connection. Domains not yet promoted still use the compatibility JSON pipeline.


## First promoted planner read: goal portfolio

The adaptive planner now has a verified Supabase read path for the goal portfolio.

- `public.training_goal_document()` exposes only the goal document that is already published on the public goal page.
- The planner prefers a direct read-only PostgreSQL connection through the existing `SUPABASE_DB_URL` GitHub secret. The `psycopg` dependency is optional/non-blocking: if installation or database access fails, planning falls back safely.
- The public RPC remains a secondary read path when a publishable key is configured; it is not required for server-side planning.
- Supabase is allowed to influence planning only when both the persisted `source_hash` and a fresh canonical hash of the returned payload exactly match the repository `data/goal.json` fallback.
- Missing configuration, driver/network/database failure or a stale database snapshot falls back to JSON without failing the training update.
- The generated strategy records whether the runtime goal source was verified Supabase or JSON fallback.

This is deliberately a read promotion, not yet a write promotion. `data/goal.json` remains the write authority/freshness oracle during this migration step. Activities and athlete state stay on the existing path until ingestion can write the database before downstream planning, avoiding one-run-old training state.


## Promoted activity and feedback runtime

Activity state is now promoted before any athlete-state or planning consumer runs.

Production order:

1. Strava event/reconcile writes the transient repository ingestion buffer.
2. Activity semantics and GUI feedback are normalized.
3. `supabase_activity_backend.py --mode promote` transactionally writes the normalized activity snapshot, laps, current overrides and append-retained feedback to Supabase.
4. A fresh read-only connection reconstructs the activity and override documents from relational rows and verifies their hashes against the persisted state-document contract.
5. Only after that verification succeeds are the JSON files materialized again as compatibility caches.
6. `build_athlete_state.py` reads its activity facts directly from the verified Supabase runtime source when `SUPABASE_DB_URL` is configured.
7. Adaptive planning therefore consumes an athlete-state built from database-backed activity facts.

This promoted path is **required** in the production update job. A database failure stops that update before athlete-state/planning; the already-published site remains intact. This is safer than silently planning from an unpersisted or stale post-ingest snapshot.

`training.activities.is_current` defines the exact latest Strava snapshot. Removed provider activities are retained historically with `is_current=false`, so they cannot reappear in athlete-state. Laps and current semantic overrides are exact-snapshot state; `activity_feedback` remains append-retained history. `training.activity_laps.lap_ordinal` is the relational identity for list position, while the original `lap_index` is preserved as source data and is allowed to duplicate in historical imports.

The later non-blocking full shadow sync remains in place for domains not yet promoted and as an independent whole-system reconciliation layer.


## Runtime authority cutover

Generated training runtime state now uses Supabase as the required commit point in
the canonical production pipeline.

The authoritative sequence is:

1. normalized activities/feedback are promoted to Supabase and independently
   read back before athlete-state is built;
2. `athlete_state` is transactionally persisted to `training.state_documents`
   and freshly read back before adaptive planning;
3. after adaptive planning, rollover, overrides and workout-design validation,
   the executable planning snapshot is written to Supabase, including
   `training_strategy`, mesocycle/microcycle documents and the current
   relational `planned_workouts` snapshot;
4. only the freshly read-back database payload is materialized to JSON for
   compatibility consumers before coach analysis;
5. after coach/device/guard processing, the final plan and coach document are
   persisted again together with relational coach evaluations;
6. rendering/publication runs from JSON compatibility caches that were
   materialized from that verified final database readback.

These runtime promotion stages are required, not best-effort. A database write,
schema, transaction verification or fresh readback failure stops the update
before the affected downstream consumer or publication step. The previously
published site remains intact.

GitHub JSON is therefore no longer the runtime source of truth for promoted
activity, athlete-state, planning or coach domains. It remains versioned as a
compatibility cache/audit artifact and as a local-development fallback where
explicitly documented.

The post-update full shadow sync remains intentionally non-blocking. Its role is
whole-system reconciliation for domains that are not yet promoted and an
independent consistency layer; it is no longer the mechanism that makes the
promoted runtime state authoritative.

## Direct training-feedback write path

Interactive post-workout feedback must not wait for the full GitHub Actions / coach /
Pages pipeline. The production write path is therefore split into two phases:

1. the Access-protected Cloudflare Worker validates the browser payload and creates
   the deterministic `training-input:<id>` event key;
2. when `SUPABASE_SECRET_KEY` (or the legacy `SUPABASE_SERVICE_ROLE_KEY`) is
   configured on the Worker, it calls the backend-only
   `public.training_submit_activity_feedback` RPC and waits only for that
   transaction to commit;
3. only after the database acknowledges the append does the Worker dispatch the
   slower `training-input-event` to GitHub Actions for intent classification,
   coach analysis, replanning, rendering and publication;
4. if GitHub dispatch fails after the database commit, the API still returns a
   saved/deferred acknowledgement. A later scheduled training run hydrates the
   append-only database feedback and resumes downstream processing.

The RPC is not granted to `anon` or `authenticated`. It is callable only through
the backend Supabase secret/service role. The secret stays in Cloudflare Worker
secret storage and must never be rendered into the site or committed to this
repository.

Every canonical training run now hydrates activities/overrides from Supabase
before Strava ingest or training-input processing. The readback first verifies
the persisted state-document hashes, then overlays newer append-only
`training.activity_feedback` events. This prevents an older generated JSON
snapshot from erasing or hiding feedback that arrived while another pipeline
run was in progress.

Operator-authored semantic corrections that originate outside the browser
feedback path live in `data/activity_directives.json`, not in the generated
`activity_overrides.json` cache. After backend hydration and provider ingest,
`apply_activity_directives.py` overlays only the explicitly named fields onto
the fresh backend projection. Newer append-only feedback and unrelated override
fields are preserved, and the merged snapshot is then promoted back to
Supabase. This keeps Supabase authoritative without making a generated Git cache
an accidental write source.

