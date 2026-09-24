# Training backend (Supabase)

This directory contains the version-controlled database contract for the training system.

## Migration status

Phase 1 is deliberately **shadow mode**:

- GitHub JSON remains the source of truth.
- The existing training pipeline and GitHub Pages rendering are unchanged.
- Supabase receives a relational copy only after the schema has been deployed and the importer has been verified.
- No browser/client access is granted in the initial migration.

The first schema separates stable domain entities (activities, feedback, plans, goals and job history) from fast-changing generated documents. Generated/derived documents can initially be mirrored in `training.state_documents` as JSONB while their long-term relational model is validated.

## Security

All tables live in the `training` schema.

Row Level Security is enabled on every table. The initial migration defines **no policies for `anon` or `authenticated`**, so the browser cannot access training data. Backend access will be introduced explicitly in a later migration.

Do not commit Supabase keys, database passwords or access tokens.

## Deployment

The Supabase GitHub integration watches `supabase/migrations/`. With production deployment enabled, pending migrations merged to the configured production branch are applied to the `hall-training` project.

The existing training application does not depend on this database yet. A migration failure therefore cannot break the live training site.

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

The UI hides the backend row when `SUPABASE_PUBLISHABLE_KEY` is absent, so deployment remains safe during configuration. Planner, coach, ingest and workout rendering still use canonical GitHub JSON.


## First promoted planner read: goal portfolio

The adaptive planner now has a verified Supabase read path for the goal portfolio.

- `public.training_goal_document()` exposes only the goal document that is already published on the public goal page.
- The planner calls that RPC with the browser-safe publishable key; no database password or service-role secret is required in the critical update job.
- Supabase is allowed to influence planning only when both the persisted `source_hash` and a fresh canonical hash of the returned payload exactly match the repository `data/goal.json` fallback.
- Missing configuration, network failure, an undeployed migration or a stale database snapshot falls back to JSON without failing the training update.
- The generated strategy records whether the runtime goal source was verified Supabase or JSON fallback.

This is deliberately a read promotion, not yet a write promotion. `data/goal.json` remains the write authority/freshness oracle during this migration step. Activities and athlete state stay on the existing path until ingestion can write the database before downstream planning, avoiding one-run-old training state.
