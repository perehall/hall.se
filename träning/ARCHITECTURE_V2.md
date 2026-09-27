# Training Architecture v2

Status: migration target. New feature work must not add dependencies on the legacy file/HTML mutation pipeline.

## Architectural invariants

1. Supabase/PostgreSQL is authoritative for promoted runtime domains.
2. Domain decisions operate on typed in-memory state, never by mutating rendered HTML.
3. JSON under `träning/data` is compatibility/export state only; new core code must not treat it as authority.
4. Publication is one-way: canonical state -> read model -> renderer -> validation -> atomic publish.
5. Rendering is pure: it receives a read model and returns output. It does not modify canonical state.
6. Provider-specific vocabulary ends at the ingest/normalization boundary.
7. Planning decisions are explainable through an explicit decision trace: goal -> mesocycle -> microcycle -> stimulus -> constraints -> workout -> dose.
8. AI may propose/interpret within an explicit contract; deterministic code owns invariants, persistence and permissions.
9. Every external event and job is idempotent and observable.
10. No new `finalize_*.py` presentation mutators. Legacy finalizers are deletion targets.

## Target modules

```
training_core/
  domain/         # typed domain entities and invariants
  repositories/   # persistence ports; Supabase/Postgres adapters
  ingest/         # Strava, feedback and wellness normalization
  planning/       # deterministic planning policy + decision trace
  coaching/       # AI boundary and conservative action policy
  application/    # use cases / transaction orchestration
  presentation/   # read-model builders and pure renderer
```

GitHub Actions invokes application use cases; it is not the application architecture.

## Runtime flow

external inputs
    -> ingest/normalization
    -> canonical PostgreSQL transaction
    -> planning/coaching use cases
    -> canonical PostgreSQL transaction
    -> presentation read model
    -> pure render
    -> validate
    -> atomic publish

A presentation failure never rolls back or invalidates canonical training state.

## Migration strategy

This is a strangler migration, not a rewrite-in-place.

Phase 0: Freeze architecture
- No new legacy finalizers.
- Add architecture contract tests.
- Record current behavioural contracts.

Phase 1: Presentation vertical slice
- [x] Build typed Today/Week read model from canonical state.
- [x] Render it once, without HTML post-processing.
- [x] Compare semantic output with production through an executable CI parity gate.
- [ ] Cut publication over after the v2 renderer carries the complete retained UI contract.
- [ ] Delete replaced finalizers.

Cutover rule: a green parity gate is necessary but not sufficient. The current
legacy page contains retained interaction/detail surfaces (feedback, workout
prescription, weather, navigation and historical detail) that are not yet part
of the minimal v2 renderer. Production must therefore remain on legacy until
those required surfaces are represented by typed read-model fields and rendered
in the same pure pass. Do not preserve them by adding post-render mutators.

Phase 2: Canonical repository boundary
- Move runtime reads/writes behind repository interfaces.
- Remove JSON as an input to migrated use cases.
- Keep JSON only as explicit export/audit compatibility until consumers are gone.

Phase 3: Planning decomposition
- Split the monolithic adaptive planner into goal, mesocycle, microcycle, stimulus, constraint and workout/dose policies.
- Persist a machine-readable decision trace for every plan decision.

Phase 4: Coaching boundary
- Separate deterministic facts and permitted actions from model interpretation.
- Persist model input/output metadata and decision linkage without leaking private wellness data.

Phase 5: Orchestration
- Replace subprocess chains with application-level Python calls and explicit transactions.
- GitHub Actions becomes a thin trigger/deploy shell.

Phase 6: Legacy deletion
- Delete compatibility JSON readers, replaced scripts/finalizers and redundant regression tests.
- Retain a compact set of domain, contract, integration and end-to-end tests.

## Definition of done

Architecture v2 is complete only when:
- canonical runtime domains can be reconstructed from PostgreSQL without Git checkout state;
- current UI is rendered from one read model in one render pass;
- no presentation finalizer mutates HTML;
- planning produces an inspectable decision trace;
- a normal update is one application workflow, not a script cascade;
- failures are visible as structured job/stage records;
- tests verify domain behaviour and boundaries rather than historical implementation accidents.
