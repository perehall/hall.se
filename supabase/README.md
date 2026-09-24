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
