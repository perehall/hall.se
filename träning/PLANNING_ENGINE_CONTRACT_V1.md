# Planning Engine Contract v1

Status: **proposed normative contract**.  
Scope: replacement of the current adaptive planning engine.  
Rule: production planning behaviour MUST NOT be changed to implement this contract until the contract itself has been reviewed and accepted.

This document defines what the planning engine is allowed to know, decide and publish. It is intentionally stricter than the current implementation. The purpose is not to reproduce today's planner. The purpose is to create a planning core whose behaviour is predictable, inspectable and testable.

Normative words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are used deliberately.

---

## 1. Core principle

The planning authority is a single deterministic domain operation:

```
canonical facts
+ athlete/goal state
+ fixed commitments
+ declared availability/preferences
+ approved workout catalog
+ previous committed plan as a stability preference only
        |
        v
candidate-plan generation
        |
        v
hard-constraint validation
        |
        v
lexicographic plan selection
        |
        v
final invariant validation
        |
        v
one atomic plan commit
```

After that commit, no downstream layer may add, remove, move, merge, split or alter training content.

Weather, coaching text, rendering, device sync and publication are projections or advisory layers. If any of them requests a training-content change, the request MUST return through the same planning authority and the affected planning window MUST be solved and validated again.

There is no post-planning "reconciliation" layer with independent authority.

### 1.1 Two planning levels, one explicit authority chain

The replacement must not make the weekly solver robust while leaving the old mesocycle generator as a hidden second authority.

Planning has two explicit levels:

1. **Strategy revision** — goal portfolio -> mesocycle intent, bounded planning obligations, protected capacities, progression axes, evaluation triggers and load-envelope policy.
2. **Execution solve** — one committed StrategyRevision + current canonical facts -> complete affected-window plan.

A StrategyRevision is immutable and versioned once committed. The execution solver never edits strategy.

For V1, a new StrategyRevision MAY be proposed by AI, but it MUST NOT become autonomous production authority merely because it validates structurally. Until an autonomous strategic-policy contract has its own acceptance tests, strategy changes require an explicit accepted revision through the coaching/user-review path.

Cutover from the legacy adaptive planner is blocked if legacy mesocycle generation can still silently change the obligations consumed by the new solver.

This keeps weekly execution deterministic while making strategic changes infrequent, inspectable and separately governable.

---

## 2. Design goals

The engine MUST be:

1. **Contract-valid by construction** — a committed plan cannot violate known hard constraints. This is not a claim that software can guarantee injury prevention or physiological safety under unknown data.
2. **Predictable** — the same frozen canonical input, strategy input and engine version produce the same plan and decision trace.
3. **Explainable** — every planned workout can be traced back to goals, evidence, constraints and selection priorities.
4. **Adaptive** — actual training can replace, satisfy, reduce, move or remove future work without relying on the old schedule as truth.
5. **Conservative under uncertainty** — missing evidence never becomes invented capacity, recovery or tolerance.
6. **Stable without being sticky** — an already valid future plan is preferred when equally good, but never preserved at the expense of stronger planning priorities.
7. **Multipass-native** — a date is a container for 0..N independent workouts; multisport workouts are explicit ordered workouts, not accidental date-level composites.
8. **Independent of presentation and providers** — no renderer, Strava vocabulary, Garmin/Intervals state or HTML structure participates in planning decisions.
9. **Extensible without special cases** — new sports or fixed loads are represented through capabilities/load dimensions and data, not weekday/date/sport-specific branches.

---

## 3. Non-goals

The engine MUST NOT:

- diagnose injury, illness or recovery state from insufficient data;
- invent threshold pace, HR, watts or exact training dose;
- infer tolerance from completion alone;
- equate different stimuli because their total duration is similar;
- optimize for calendar fullness;
- copy elite training templates directly;
- use rendering concerns to change training;
- use device-sync success/failure to determine physiological planning;
- silently relax hard constraints to produce a prettier week.

---

## 4. Canonical inputs

The solver receives one immutable `PlanningInput`. It MUST contain only typed canonical domain data.

### 4.1 Athlete facts

Examples:

- canonical completed activities;
- explicit activity semantics/capabilities;
- explicit athlete feedback;
- capability state: demonstrated, tolerated, absorbed;
- progression readiness and evidence;
- recent load/exposure windows;
- available performance markers;
- recovery/wellness context when explicitly available and permitted.

Facts and interpretation MUST be distinguishable. A missing fact is `unknown`, never an assumed normal value.

### 4.2 Goal state

The engine receives the already resolved strategic/mesocycle intent:

- primary development capabilities;
- secondary capabilities;
- protected/maintenance capacities;
- competition context;
- block intent: establish/develop/consolidate/review/reduce;
- progression axes;
- success criteria.

The execution solver MUST NOT independently reinterpret the complete goal portfolio into a different strategy. It consumes one committed StrategyRevision.

The strategic layer MUST materialize bounded **planning obligations** rather than only broad labels such as "primary" or "protected". Each obligation MUST have a stable id and declare, where applicable:

- capability/stimulus;
- role and priority class;
- minimum required exposure count;
- maximum useful exposure count;
- permitted recipe family;
- whether partial coverage is allowed and the exact mapping that grants it;
- authorized progression axis/axes;
- validity window.

The solver may only create a non-fixed workout when it can reference an explicit planning obligation or an explicit user request. This prevents "more training" from improving the objective merely by adding duplicate sessions.

### 4.3 Athlete-declared constraints and preferences

Examples:

- unavailable days/time windows;
- preferred training frequency;
- attitude to double sessions;
- fixed personal commitments;
- preferred surfaces/locations when relevant;
- explicit user-confirmed future sessions.

A declared availability restriction is a hard constraint. A frequency preference is normally a soft objective.

### 4.4 Approved workout catalog

The catalog is the sole source for executable dose options.

A recipe MUST declare:

- capabilities/stimuli trained;
- load dimensions;
- dose axis and approved dose options;
- role eligibility;
- compatibility metadata needed by constraints;
- executable prescription if device materialization is expected.

AI or planner code MUST NOT fabricate a missing dose step.

### 4.5 External/fixed training load

Enduro, races, group sessions and similar commitments are represented as generic `FixedLoadCommitment` objects.

A fixed load MUST carry explicit load semantics, for example:

- mechanical leg load;
- cardiovascular load;
- neuromuscular/plyometric load;
- technical load;
- upper-body load;
- duration certainty/uncertainty;
- expected recovery interaction category where established.

The planner MUST NOT require code such as "if sport == enduro and weekday == Monday". Enduro is one data instance of a generic external-load model.

### 4.6 Previous committed plan

The previous plan is NOT a fact about what should still happen.

It is used only for the soft objective **plan stability**. Any previous workout that conflicts with stronger priorities or newly observed facts is discarded by normal candidate selection. It is never reinserted afterward.

### 4.7 Source revision and canonicalization

Every planning input MUST carry a monotonic or otherwise concurrency-safe source revision plus a canonical semantic hash.

The hash MUST exclude incidental ordering, generated timestamps and transport metadata. Equivalent semantic inputs therefore hash identically.

The final plan records:
- source revision;
- semantic input hash;
- strategy/mesocycle revision;
- catalog/policy version;
- engine version.

A plan whose source revision no longer matches current canonical planning state is **stale**, even if its content was previously valid.

---

## 5. Planning window

Planning operates on an **affected window**, not on an isolated date.

The window MUST include:

- all mutable dates whose workouts may change;
- at least the preceding 3 calendar days as load/context evidence;
- at least the following 3 calendar days for adjacency and fixed-commitment effects;
- any additional dates required to close a constraint that crosses the initial boundary.

Past completed dates are context only and immutable.

The normal current-week planning operation SHOULD solve the complete active microcycle as one unit. Near a week boundary, the window MUST include enough of the following week to evaluate cross-boundary constraints.

---

## 6. Workout identity model

A `PlannedWorkout` is an independently addressable physical workout.

Minimum fields:

- stable workout identity;
- date;
- optional declared time window or within-day order;
- ordered components if explicitly multisport;
- recipe identity;
- selected catalog dose option;
- capabilities/stimuli;
- load dimensions;
- strategic role;
- planning status;
- fixed/manual constraint references;
- decision-trace reference.

Rules:

- One date may contain 0..N independent workouts.
- Independent swim + strength remain two workouts.
- A brick, swimrun or triathlon session is one workout only when intentionally modeled with ordered components.
- A date is never a workout identity.
- Renderer grouping MUST NOT alter workout semantics.
- Same-day ordering/separation MUST be represented explicitly when it matters to compatibility.
- The engine MUST NOT invent clock times. If exact timing is unknown, it may use only abstract order/separation states supported by the input and catalog.

---

## 7. Hard constraints

A candidate violating any hard constraint is invalid and MUST NOT be committed.

Hard constraints are central domain rules. They are not scattered post-processing checks.

### H1. Actual-truth precedence

Completed canonical activities are immutable facts and outrank prescription.

The planner MUST NOT:

- delete or rewrite completed activity truth;
- present a planned session as completed instead;
- re-prescribe an already satisfied stimulus merely because the originally planned calendar slot is still in the future.

### H2. Past immutability

Closed/past dates MUST NOT receive new planned workouts or be moved retrospectively.

### H3. Fixed commitments

A user-confirmed fixed commitment MUST remain in the plan unless the user explicitly changes/removes it or a higher-order safety state makes all planning fail closed for review.

Fixed commitments are solver inputs, never downstream overrides.

### H4. Availability

No workout may be placed in a declared unavailable window.

### H5. Catalog-only executable dose

Every non-external planned workout MUST resolve to an approved recipe/dose option. No invented dose is permitted.

### H6. Evidence-bound progression

Automatic progression MUST require the capability's explicit progression readiness contract.

Completion alone is not tolerance. Demonstrated maximum is not absorbed dose.

Progression is multi-axis. The engine MUST treat at least the following as potential progression:
- per-session dose;
- intensity or intensity-density;
- repetition/exposure count;
- reduced recovery;
- mechanical demand;
- specificity;
- total microcycle exposure in the capability/load dimension.

The engine MUST NOT hold per-session dose constant while silently progressing training by adding another exposure or increasing another axis unless that axis is explicitly authorized by the mesocycle and supported by progression evidence.

When absorbed/tolerated evidence is absent, a self-reported starting level MAY act as an establishment ceiling, but fresher verified demonstrated evidence with caution MUST cap that starting level conservatively.

### H7. Stimulus identity

One capability may satisfy another only through an explicit capability mapping.

Duration similarity, distance similarity or same sport MUST NOT create planning credit across unrelated stimuli.

Example: a completed run-threshold session does not satisfy an easy-distance development obligation merely because total session time is comparable.

### H8. Load compatibility

Every planned session and every relevant rolling interaction window MUST satisfy generic load-compatibility constraints based on load dimensions and recovery interaction, not sport names or weekdays.

The horizon is defined by the constraint itself; it is NOT limited to adjacent days. Same-day, 24 h, 48 h, 72 h or longer interactions may exist when explicitly modeled.

Compatibility MAY be asymmetric. A load dimension occurring before another may require a different separation than the reverse order; the engine MUST NOT collapse both directions into one symmetric rule when the policy distinguishes them.

This includes same-day multipass compatibility, order and separation.

The constraint system MUST be able to express:

- incompatible high mechanical-load clustering;
- high-quality run spacing restrictions;
- external-load recovery interaction;
- MTB/technical mechanical interaction;
- strength/plyometric interference;
- same-day order/separation requirements;
- explicitly permitted low-conflict doubles.

The catalog/load model owns these semantics. Unknown load interaction MUST NOT be treated as proven compatibility.

### H9. Cross-boundary validity

A workout may not be valid merely because the conflicting workout falls outside the current calendar week. Constraints MUST operate across the full affected window.

### H10. No silent hard-constraint relaxation

If no valid candidate exists, the engine MUST return `NoValidPlan` with explicit unsatisfied constraints.

It MUST NOT silently:
- drop a fixed commitment;
- invent capacity;
- increase tolerated dose;
- ignore availability;
- weaken a load constraint.

A newly persisted canonical fact MUST NOT leave an older plan falsely presented as current. `NoValidPlan` therefore commits a **PlanningBlocked** state for the new source revision. The last valid plan remains available for audit, but it is no longer authoritative for the affected mutable window.

A PlanningBlocked state:
- preserves completed truth and fixed commitments as context;
- contains no newly invented mutable prescription;
- identifies which previous future workouts are no longer current;
- blocks fresh device delivery of stale mutable workouts;
- requires explicit resolution/replanning before those workouts can again be presented as current prescription.

### H11. Single-authority finality

The plan that passes final invariant validation is the only plan allowed to be committed.

No later stage may alter training content.

### H12. Determinism

Given:
- identical canonical input,
- identical catalog/policy versions,
- identical engine version,

the selected plan and machine-readable decision trace MUST be semantically identical regardless of input ordering, process timing or API response ordering.

### H13. Canonical multipass integrity

No migration or planner stage may merge independent same-day workouts or split one intentional multisport workout based on date or text parsing.

### H14. Unknown-data conservatism

Unknown recovery, tolerance, classification or capacity MUST NOT be converted into a positive claim.

When a decision depends on missing evidence and no safe catalog option exists, the engine MUST hold/reduce/defer rather than invent.

### H15. Workout justification and bounded obligations

Every non-fixed planned workout MUST reference at least one explicit planning obligation or explicit user request.

An obligation MUST define a bounded useful exposure range. Additional duplicate workouts beyond that range cannot improve the objective vector and MUST NOT be generated as calendar filler.

### H16. Aggregate load envelope

Per-session validity is insufficient. The complete candidate plan MUST fit an explicit aggregate load envelope derived from canonical athlete state, mesocycle policy and approved establishment/progression rules.

The envelope MAY use categorical or numeric bounds, but every bound must have provenance. It MUST NOT fabricate TSS, recovery scores or precision that the input does not support.

The envelope MUST be able to bound, where supported by evidence:
- total exposure count per capability;
- cumulative duration/distance/dose;
- quality-session count;
- high-mechanical-load count;
- rolling load in relevant load dimensions.

When no trusted aggregate bound exists, automatic planning MUST NOT increase aggregate exposure above the most recent established comparable baseline solely to satisfy lower-priority objectives. A confirmed starting state may establish an initial ceiling; fresher caution evidence may lower it.

A load bound MAY declare that its metric requires complete coverage across every relevant observed, fixed and planned exposure in its rolling window. When such coverage is incomplete, unknown load MUST NOT be treated as zero. A candidate that adds mutable training is invalid until the bound can be proven; a zero-new-training/defer outcome may remain valid. The envelope's unknown policy must therefore be executable validation semantics, not descriptive metadata.

### H17. Immutable plan content versus delivery metadata

A committed `PlanContent` has a content hash. Downstream systems MAY attach delivery/publication metadata, but MUST NOT change anything that affects workout identity, date, recipe, dose, components, load semantics or planning status without a new solve and commit.

Device-sync status, renderer state and publication timestamps therefore live outside the immutable training-content hash.

### H18. Concurrency-safe commit

Planning uses optimistic concurrency.

A solver result may commit only if the canonical source revision used to build `PlanningInput` is still current at commit time. If a newer activity, feedback event, availability change or commitment arrives during solving, the commit MUST abort and the engine MUST solve again from the new revision.

Duplicate events and duplicate planning triggers MUST be idempotent.

### H19. Proven selection within the bounded candidate domain

The solver MUST NOT silently commit a heuristic or time-limited approximation as if it were the selected optimum.

Within the explicitly bounded candidate domain, the committed plan MUST either:
- be proven lexicographically optimal under the objective order; or
- use a deterministic selection algorithm whose completeness for that domain is established by design.

If search is incomplete or resource limits are hit before this can be established, the outcome is a planning failure, not a lower-quality silent commit.

### H20. Planner-introduced versus immutable conflicts

Hard compatibility rules constrain what the planner is allowed to add.

If user-declared/fixed commitments themselves create an unavoidable conflict, the engine MUST NOT rewrite those commitments to manufacture validity. It records the immutable conflict, adds no mutable work that worsens it, and returns PlanningBlocked or an explicitly constrained plan state according to policy.

This distinction preserves user agency while preventing the planner from compounding an already fixed load conflict.

---

## 8. Soft objectives and deterministic priority

Among valid candidates, selection uses a **lexicographic objective vector**. We do not use an opaque weighted score whose trade-offs are difficult to predict.

Earlier objectives always outrank later ones.

### S1. Fulfil planning obligations by declared priority tier

Minimize unmet bounded obligations in explicit priority-tier order. Primary, protected and maintenance roles do not receive hidden priority merely from their names; the committed StrategyRevision defines their tier.

Do not reward duplicate coverage beyond an obligation's maximum useful exposure count.

### S2. Preserve breadth within equal-priority obligations

When obligations share the same priority tier, prefer meeting their minimum useful exposure across the declared capability portfolio before adding extra exposure above another obligation's minimum. This prevents one capability from crowding out equally important protected breadth.

### S3. Avoid discretionary exposure / calendar filler

Once required obligations are equally satisfied, prefer the plan with less exposure above obligation minima.

A declared training-frequency preference is never, by itself, a reason to create another workout. If additional exposure is strategically desired, that intent must exist in StrategyRevision as a higher minimum obligation.

### S4. Absorbable distribution

Prefer better spacing of repeated/high-load stimuli and avoid unnecessary concentration of mechanical or quality load.

### S5. Plan stability

Minimize unnecessary changes to still-valid future workouts from the previous committed plan.

This objective is deliberately below physiological/strategic validity and the anti-filler rule. Stability never resurrects an inferior, conflicting or no-longer-justified old workout.

### S6. Athlete schedule preferences

Prefer declared training-frequency range and double-session preference only when distributing already-justified training.

### S7. Useful discipline/character variation

Prefer planned variation when the mesocycle calls for development and valid catalog alternatives exist.

### S8. Canonical tie-break

When two candidates are still equivalent, select using stable canonical ordering:
1. earlier recipe priority defined by the mesocycle/catalog;
2. earlier valid date;
3. stable recipe id;
4. stable dose-option id.

No randomness is permitted in production plan selection.

---

## 9. Candidate generation

The engine MUST reason over **complete candidate plans**, not greedily mutate one calendar day at a time and then repair consequences.

The candidate domain MUST be explicitly bounded by planning obligations, approved recipe/dose options, fixed commitments and valid placement windows. A valid implementation may use deterministic backtracking, branch-and-bound or a constraint solver. The contract does not assume exhaustive naive enumeration will always be small.

Conceptually:

1. Determine remaining bounded planning obligations from mesocycle intent minus valid actual-work credit.
2. Determine allowable catalog recipes/doses and aggregate exposure bounds from capability state.
3. Create placement domains for every candidate workout.
4. Include fixed commitments as immutable placements.
5. Search combinations.
6. Reject candidates immediately on hard-constraint violation.
7. Calculate lexicographic objective vector for valid candidates.
8. Select the best candidate deterministically.
9. Run the complete final invariant suite again on the exact selected plan.
10. Commit once.

An optimizer library is optional. Correctness and inspectability matter more than sophistication.

---

## 10. Replanning semantics

Replanning is a new solve, not mutation repair.

Triggers may include:

- new completed activity;
- edited/corrected activity semantics;
- athlete feedback;
- changed availability;
- changed fixed commitment;
- relevant recovery input;
- goal/mesocycle change;
- explicit user request to move/add/remove a planned workout.

Procedure:

1. Persist/normalize the new canonical fact first.
2. Rebuild athlete/capability facts.
3. Determine affected planning window.
4. Treat the previous future plan as a stability preference only.
5. Re-solve the complete affected window.
6. Validate the complete candidate.
7. Commit atomically.
8. Project the committed result to UI/device sync.

There is no later "preserve unaffected workouts" mutation stage. Preservation is part of the plan-stability objective during the solve.

### 10.1 Spontaneous actual workout

A spontaneous workout is classified from canonical activity semantics.

It may:
- satisfy an intended stimulus;
- partially satisfy a requirement when an explicit mapping says so;
- add load that changes placement/dose of future work;
- cause an originally planned workout to disappear.

It MUST NOT trigger a simplistic "move the missed workout to the next free day" rule.

### 10.2 Missed workout

A missed workout is not automatically debt.

The engine reassesses whether the stimulus is still needed inside the current mesocycle and whether it can be absorbed in the remaining window.

### 10.3 User-requested move

A requested move becomes an input constraint/request and is solved against the whole affected window. The UI MUST NOT directly rewrite the date.

---

## 11. AI boundary

AI is advisory and constrained.

AI MAY:
- interpret qualitative athlete feedback;
- propose strategic emphasis;
- propose recipe character from an approved set;
- explain trade-offs;
- request a replan with structured reasons.

AI MUST NOT:
- write the canonical plan;
- bypass hard constraints;
- create a new dose;
- create provider/device payloads as planning truth;
- preserve/reinsert workouts after the solver;
- determine whether final invariants pass.

All AI proposals are untrusted inputs until deterministic validation succeeds.

The engine MUST have a deterministic fallback that can produce a valid conservative plan or `NoValidPlan` without AI.

AI interpretation MUST NOT create or relax hard constraints, progression readiness, tolerance/absorption facts or canonical activity semantics on its own. If an AI interpretation is to affect those domains, it must first become an explicit versioned canonical input through a deterministic rule or user-confirmed action. Frozen canonical interpretation is part of the input hash; model sampling is never part of plan selection.

---

## 12. Decision trace

Every committed plan MUST have a machine-readable `PlanningDecisionTrace`.

At minimum:

- engine/version hashes;
- canonical input hash;
- affected planning window;
- completed-activity credits and why they count;
- remaining primary/protected obligations;
- hard constraints applied;
- candidate count considered/rejected;
- rejection reason codes;
- selected objective vector;
- for each planned workout:
  - why this stimulus exists;
  - why this recipe;
  - why this dose;
  - why this date;
  - which alternatives lost and on which higher-priority objective;
- differences from previous committed plan;
- explicit reason for every removed/moved workout;
- final invariant result;
- source revision and commit revision;
- search/optimality status;
- stale/fresh plan status.

The trace need not enumerate every combinatorial candidate. It MUST record the decisive alternatives and objective/constraint reasons needed to explain the selected result, plus aggregated rejection/search statistics.

Public UI may summarize this, but the canonical trace remains inspectable.

---

## 13. Failure semantics

The planner MUST fail closed.

### `NoValidPlan`

Returned when hard constraints make the requested planning intent impossible.

Contains:
- conflicting hard constraints;
- involved dates/workouts/commitments;
- what strategic obligations remain unsatisfied;
- whether user input is required.

### Technical failure

A technical failure MUST NOT publish a partially mutated plan.

If canonical planning inputs have not changed, the last committed valid plan remains authoritative.

If canonical planning inputs HAVE changed, the previous plan becomes stale because its source revision no longer matches current facts. The application layer MUST expose that stale state and MUST NOT present affected future workouts as a freshly validated current prescription. Device delivery for newly stale mutable content is blocked until planning succeeds or an explicit PlanningBlocked state is committed.

### Invariant failure

Any final invariant failure is a programming defect and blocks commit.

It is never auto-repaired downstream.

---

## 14. Architecture boundary

New implementation lives under:

```
training_core/planning/
  models.py
  constraints/
  candidate_generation.py
  objectives.py
  solver.py
  validation.py
  trace.py
  service.py
```

Exact filenames may change, but responsibilities MUST remain separated.

The new planning core MUST NOT:
- import legacy `scripts/adaptive_planner.py`;
- read/write `träning/data/*.json` directly;
- import renderer/finalizer code;
- invoke subprocesses;
- call provider APIs;
- depend on GitHub Actions;
- mutate Supabase directly from domain code.

Repositories/application services own persistence and transactions.

---

## 15. Mandatory test strategy

Green example tests are necessary but not sufficient.

### 15.1 Unit tests

Every hard constraint and soft objective has direct unit tests.

### 15.2 Property-based / generative tests

Generate many combinations of:

- 0..N workouts per day;
- completed/spontaneous activities;
- fixed external loads;
- unavailable days;
- capability states;
- dose catalogs;
- double-session preferences;
- week-boundary positions;
- prior committed plans.

Minimum properties:

1. Every committed result passes all hard invariants.
2. Same semantic input always produces the same output.
3. Re-running with no input change is idempotent.
4. Past completed truth never changes.
5. Input ordering does not change output.
6. Independent same-day workouts never merge.
7. No post-commit projection can change training content.
8. Unsupported progression is impossible.
9. Cross-stimulus scalar similarity never creates planning credit.
10. If no valid plan exists, solver returns `NoValidPlan` rather than an invalid plan.

The CI target is at least **10,000 generated planning cases** per full planning-core test run, using reproducible seeds. This number is a stress target, not evidence by itself that the planner is correct.

Generative coverage MUST additionally include:
- boundary values for every hard constraint;
- pairwise interaction coverage across hard constraints and objective classes;
- multi-event sequences, not only static snapshots;
- concurrency/interleaving tests;
- mutation tests proving that weakening/removing a hard guard causes tests to fail.

### 15.3 Metamorphic tests

Examples:

- shuffle activity/input order -> identical plan;
- run identical replan twice -> identical plan;
- add irrelevant history outside the evidence horizon -> identical plan;
- add a spontaneous completed primary stimulus -> the same primary requirement cannot also remain merely because its old slot existed;
- replace a completed workout with a different stimulus of equal duration -> planning credit changes according to semantics, not duration;
- remove availability -> candidate space may expand, never by mutating past truth;
- cross a Sunday/Monday week boundary -> rolling compatibility constraints remain identical;
- increase exposure count while holding per-session dose constant -> progression guard still applies;
- add a concurrent feedback/activity event during solve -> stale solver result cannot commit;
- downstream device/publication metadata changes -> PlanContent hash remains identical.

### 15.4 Historical replay

Replay all available canonical history available to the project, with a minimum target of the last 8 weeks, through the new engine. Historical evidence horizons used by athlete-state reconstruction may extend further than the mutable planning window.

The replay MUST:
- never violate a hard invariant;
- produce a complete decision trace at every replan point;
- remain deterministic across repeated replay;
- surface every `NoValidPlan` explicitly.

Human review compares decisions with known training context; the test does not force the new engine to reproduce legacy decisions.

---

## 16. Curated scenario suite

These scenarios are acceptance fixtures. Expected results should generally assert properties/intent, not brittle exact dates unless the date itself is the constraint under test.

1. Normal week with no deviations.
2. Spontaneous threshold workout before planned threshold.
3. Spontaneous easy run before planned quality.
4. Missed swim with enough remaining capacity.
5. Missed swim with no absorbable remaining slot.
6. Two completed activities on one day.
7. Three planned independent workouts on one day when explicitly permitted.
8. Explicit brick/multisport workout.
9. Fixed external high-leg-load commitment.
10. Fixed commitment immediately after the active week boundary.
11. User unavailable day.
12. User moves one future workout.
13. New heavy/caution feedback after an easy-distance exposure.
14. Completed workout without feedback: demonstrated but not automatically tolerated/absorbed.
15. High onboarding/start value contradicted by fresher demonstrated evidence.
16. Two swim exposures: spacing preferred when possible.
17. Same-day swim + strength: allowed only from generic compatibility/preferences.
18. Quality run + incompatible mechanical load: rejected by load dimensions.
19. Equal-duration threshold vs easy-distance: no cross-credit.
20. Completed enduro/external load replaces other load when needed; it is not automatically added on top.
21. Week rollover with multipass.
22. Plan re-run with no new facts: zero semantic changes.
23. Prior plan contains a now-invalid old workout: stability objective cannot resurrect it.
24. No valid placement exists: `NoValidPlan`.
25. Unknown activity type: conservative semantics, no fabricated training credit.
26. Reduced availability after plan commit: full affected-window replan.
27. Goal/mesocycle transition.
28. Develop microcycle with progression-ready=true: at most the permitted progression axis/step.
29. Develop microcycle without progression evidence: explicit consolidation/hold.
30. Device-sync failure after commit: canonical plan remains unchanged.
31. Added second exposure with unchanged per-session dose: treated as progression.
32. Total microcycle load exceeds established envelope despite individually valid sessions: rejected.
33. Two fixed commitments create unavoidable conflict: user commitments remain, planner adds no worsening load and surfaces blocked/constrained state.
34. New canonical activity arrives while solver is running: stale solve cannot commit.
35. Planner returns NoValidPlan after a new activity: old future prescription is not silently left current.
36. Technical planning failure after new canonical facts: previous plan is marked stale and affected device delivery is blocked.
37. Same-day double where order matters but exact times are unknown: engine uses declared abstract order/separation and never invents clock times.
38. AI interpretation changes wording but canonical facts do not change: plan remains identical.
39. Equivalent input with shuffled ordering/timestamps: semantic input hash and plan remain identical.
40. Search limit/resource exhaustion: no approximate plan is silently committed.

New production defects MUST normally expand a general property/constraint test. A new scenario fixture is added only when it represents a genuinely distinct domain situation, not to patch one date/sport combination.

---

## 16.1 Shadow-input readiness gate

Shadow mode MUST NOT be fed by an implicit translation of legacy planner output.

Before any live shadow solve, the application layer must materialize the following V1 projections directly from canonical sources, each with source revision and provenance:

- one accepted `StrategyRevision` containing bounded planning obligations;
- approved workout options with explicit load semantics and executable dose identity;
- athlete-specific `OptionEligibility` derived without importing legacy planner decisions;
- canonical observed obligation credits;
- canonical observed categorical and quantitative load exposures;
- fixed commitments;
- declared availability;
- one explicit load-compatibility policy;
- one explicit aggregate load envelope.

The bridge MUST fail closed when any required projection cannot be justified from canonical data.

In particular, it is prohibited to:
- infer weekly exposure minima/maxima from old calendar placement alone;
- treat legacy planner output as evidence of athlete tolerance;
- synthesize an aggregate load ceiling merely from a convenient recent total;
- import `adaptive_planner.py` or any legacy reconciliation function to populate V1 contracts;
- silently downgrade unknown load semantics to low load or compatibility.

A shadow run is considered **input-ready** only when the complete `PlanningSolveRequest` can be reconstructed from these V1 projections without consulting legacy planning decisions except as the optional previous-plan stability input.

## 17. Cutover criteria

The new engine MUST NOT become production authority until all conditions are met.

### Code/architecture

- New planning core has no dependency on legacy adaptive planner or JSON mutation pipeline.
- Legacy mesocycle generation cannot silently feed/change obligations after cutover.
- StrategyRevision ownership is explicit and versioned.
- There is exactly one training-content execution authority.
- Manual overrides, coach suggestions and actual-driven replanning enter as solver inputs.
- No stage after final plan commit can alter training content.
- UI and device sync consume the same committed plan snapshot.

### Verification

- 100% hard-constraint unit tests green.
- Curated scenario suite green.
- At least 10,000 reproducible generated cases green.
- Boundary, interaction, sequence, concurrency and mutation-test suites green.
- Historical replay over all available project history (minimum 8 weeks) has zero hard-invariant breaches.
- Deterministic replay produces identical semantic output on repeated runs.
- Failure-injection tests prove no partial plan publication and no stale plan can masquerade as current.
- Solver optimality/completeness contract is verified for the bounded candidate domain.

### Shadow mode

Before cutover, the new engine runs in shadow against real inputs.

Required:
- at least four complete live microcycles;
- at least 20 genuine live replanning events;
- every replan event recorded with decision trace;
- deliberate review of spontaneous-workout, multipass, fixed-load, user-change and week-boundary cases (live where they occur, otherwise deterministic replay fixtures);
- zero unexplained hard-invariant failures;
- zero stale/obsolete solver commits under concurrent-event tests;
- any surprising valid decision must be explainable from the documented objective order, not from hidden special cases.

### Human acceptance

A human reviewer must be able to answer for every changed workout:

1. What new fact triggered this?
2. Which obligation/constraint changed?
3. Why was this workout kept/moved/removed?
4. Which higher-priority objective defeated the alternatives?
5. Did the final published/device plan come from this exact committed snapshot?

If those answers are not available, cutover is blocked even if CI is green.

---

## 18. Migration rule

The current planner remains production authority while the new engine is built.

During migration:

- do not add new planning behaviour to legacy unless required to keep production operational;
- do not port legacy conditionals automatically;
- every legacy behaviour must earn its place as a domain fact, hard constraint, soft objective or be deleted;
- shadow output must never mutate production;
- cutover is one authority switch, not a permanent hybrid of two planners.

After cutover, remove the legacy planning/reconciliation paths rather than keeping them as fallback writers.

---

## 19. Definition of trustworthiness

"Skottsäker" does not mean the engine always chooses the same workout a human coach would choose.

It means:

- it never violates its declared hard rules for the facts it actually knows;
- it never claims that contract validity is a guarantee against injury or bad outcomes under unknown information;
- it never invents missing evidence;
- it never hides conflicting constraints;
- it cannot be changed after validation by another layer;
- identical inputs produce identical decisions;
- every decision has an inspectable reason;
- unexpected real-life events cause a complete, bounded replan rather than patch accumulation;
- when the system cannot produce a valid plan, it says so instead of fabricating one.

That is the standard this engine must meet before it is trusted as autonomous planning authority.
