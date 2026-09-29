const DEFAULT_REPOSITORY = "perehall/hall.se";
const DEFAULT_EVENT_TYPE = "strava-activity-event";
const DEFAULT_TRAINING_INPUT_EVENT_TYPE = "training-input-event";
const DEFAULT_ATHLETE_PLAN_EVENT_TYPE = "athlete-profile-plan-request";
const TRAINING_INPUT_PATH = "/träning/training-api/input";
const ATHLETE_PROFILE_PATH = "/träning/training-api/profile";
const ATHLETE_STARTING_STATE_PATH = "/träning/training-api/profile/starting-state";
const ATHLETE_PLAN_GENERATE_PATH = "/träning/training-api/profile/generate";
const DEFAULT_TRAINING_INPUT_HOST = "xn--hll-qla.se";
const TRAINING_INPUT_OPERATIONS = new Set(["ADD_FEEDBACK", "UPDATE_COMPLETED_WORKOUT", "ADD_SPONTANEOUS_WORKOUT", "REPORT_PAIN", "REPORT_FATIGUE", "NATURAL_LANGUAGE"]);
const TRAINING_INPUT_FEELINGS = new Set(["fresh", "tired", "strong_legs", "heavy_legs", "pain", "could_do_more"]);
const DEFAULT_GITHUB_API_VERSION = "2026-03-10";
const DEFAULT_TIMEOUT_MS = 1500;
const DEFAULT_SUPABASE_PROJECT_URL = "https://izzevnhgtsvffpkccoai.supabase.co";
const TRAINING_FEEDBACK_RPC_PATH = "/rest/v1/rpc/training_submit_activity_feedback";
const ATHLETE_PROFILE_GET_RPC_PATH = "/rest/v1/rpc/training_get_athlete_profile";
const ATHLETE_PROFILE_UPSERT_RPC_PATH = "/rest/v1/rpc/training_upsert_athlete_profile";
const ATHLETE_STARTING_STATE_GET_RPC_PATH = "/rest/v1/rpc/training_get_athlete_starting_state";
const ATHLETE_STARTING_STATE_UPSERT_RPC_PATH = "/rest/v1/rpc/training_upsert_athlete_starting_state";
const ATHLETE_PLAN_REQUEST_RPC_PATH = "/rest/v1/rpc/training_request_plan_generation";
const ATHLETE_PLAN_GET_RPC_PATH = "/rest/v1/rpc/training_get_plan_generation";
const ATHLETE_PLAN_STATUS_RPC_PATH = "/rest/v1/rpc/training_set_plan_generation_status";
const DEFAULT_SUPABASE_TIMEOUT_MS = 2500;

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function configured(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function supabaseSecretKey(env) {
  if (configured(env.SUPABASE_SECRET_KEY)) return env.SUPABASE_SECRET_KEY.trim();
  if (configured(env.SUPABASE_SERVICE_ROLE_KEY)) return env.SUPABASE_SERVICE_ROLE_KEY.trim();
  return "";
}

function directTrainingInputPersistenceConfigured(env) {
  return configured(supabaseSecretKey(env));
}

function accessAssertion(request) {
  return String(request.headers.get("cf-access-jwt-assertion") || "").trim();
}

function decodeAccessClaim(assertion) {
  try {
    const parts = assertion.split(".");
    if (parts.length < 2) return {};
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return {};
  }
}

async function athleteSubjectFromRequest(request) {
  const assertion = accessAssertion(request);
  if (!assertion) return "";
  const claim = decodeAccessClaim(assertion);
  const identity = String(
    request.headers.get("cf-access-authenticated-user-email")
      || claim.email
      || claim.sub
      || ""
  ).trim().toLowerCase();
  if (!identity) return "";
  return "access:" + (await sha256Hex("cf-access:" + identity)).slice(0, 32);
}

function validIsoDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export function validateAthleteProfile(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, status: 400, reason: "invalid_profile" };
  }
  const allowed = new Set([
    "schema_version", "status", "current_step", "goals", "availability",
    "preferences", "constraints", "coach_autonomy",
  ]);
  if (Object.keys(payload).some((key) => !allowed.has(key))) {
    return { ok: false, status: 400, reason: "unexpected_profile_fields" };
  }
  if (payload.schema_version !== 1) {
    return { ok: false, status: 400, reason: "invalid_profile_version" };
  }
  if (!["draft", "complete"].includes(payload.status)) {
    return { ok: false, status: 400, reason: "invalid_profile_status" };
  }
  if (!Number.isInteger(payload.current_step) || payload.current_step < 0 || payload.current_step > 9) {
    return { ok: false, status: 400, reason: "invalid_profile_step" };
  }

  const rawGoals = payload.goals ?? [];
  if (!Array.isArray(rawGoals) || rawGoals.length > 8) {
    return { ok: false, status: 400, reason: "invalid_goals" };
  }
  const goals = [];
  for (const goal of rawGoals) {
    if (!goal || typeof goal !== "object" || Array.isArray(goal)) {
      return { ok: false, status: 400, reason: "invalid_goal" };
    }
    const goalKeys = new Set(["text", "target_date", "importance"]);
    if (Object.keys(goal).some((key) => !goalKeys.has(key))) {
      return { ok: false, status: 400, reason: "invalid_goal" };
    }
    if (typeof goal.text !== "string" || goal.text.length > 500) {
      return { ok: false, status: 400, reason: "invalid_goal_text" };
    }
    const goalText = goal.text.trim();
    // Drafts are intentionally incomplete. The UI starts with one blank goal
    // row, which is a presentation placeholder and must not make autosave fail.
    // Blank rows are discarded server-side; completed profiles still require
    // at least one real goal below.
    if (!goalText) {
      if (payload.status === "draft") continue;
      return { ok: false, status: 400, reason: "invalid_goal_text" };
    }
    if (goalText.length < 3) {
      return { ok: false, status: 400, reason: "invalid_goal_text" };
    }
    if (goal.target_date != null && goal.target_date !== "" && !validIsoDate(goal.target_date)) {
      return { ok: false, status: 400, reason: "invalid_goal_date" };
    }
    if (goal.importance != null && !["primary", "equal", "secondary"].includes(goal.importance)) {
      return { ok: false, status: 400, reason: "invalid_goal_importance" };
    }
    goals.push({
      text: goalText,
      target_date: goal.target_date || null,
      importance: goal.importance || "equal",
    });
  }

  const availability = payload.availability ?? {};
  if (!availability || typeof availability !== "object" || Array.isArray(availability)) {
    return { ok: false, status: 400, reason: "invalid_availability" };
  }
  const days = new Set(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]);
  for (const [day, value] of Object.entries(availability)) {
    if (!days.has(day) || !value || typeof value !== "object" || Array.isArray(value)) {
      return { ok: false, status: 400, reason: "invalid_availability" };
    }
    if (typeof value.available !== "boolean") {
      return { ok: false, status: 400, reason: "invalid_availability" };
    }
    if (value.minutes != null && (!Number.isInteger(value.minutes) || value.minutes < 15 || value.minutes > 480)) {
      return { ok: false, status: 400, reason: "invalid_availability_minutes" };
    }
  }

  const preferences = payload.preferences ?? {};
  if (!preferences || typeof preferences !== "object" || Array.isArray(preferences)) {
    return { ok: false, status: 400, reason: "invalid_preferences" };
  }
  const preferenceKeys = new Set(["frequency","double_sessions","rest_days","facilities","likes","dislikes"]);
  if (Object.keys(preferences).some((key) => !preferenceKeys.has(key))) {
    return { ok: false, status: 400, reason: "invalid_preferences" };
  }
  const frequency = preferences.frequency ?? {};
  if (!frequency || typeof frequency !== "object" || Array.isArray(frequency)) {
    return { ok: false, status: 400, reason: "invalid_frequency" };
  }
  const frequencyKeys = new Set(["preferred_days","min_days","max_days"]);
  if (Object.keys(frequency).some((key) => !frequencyKeys.has(key))) {
    return { ok: false, status: 400, reason: "invalid_frequency" };
  }
  const frequencyValues = ["preferred_days","min_days","max_days"].map((key) => frequency[key]);
  if (frequencyValues.some((value) => value != null && (!Number.isInteger(value) || value < 1 || value > 7))) {
    return { ok: false, status: 400, reason: "invalid_frequency" };
  }
  if (frequencyValues.every((value) => Number.isInteger(value))) {
    if (!(frequency.min_days <= frequency.preferred_days && frequency.preferred_days <= frequency.max_days)) {
      return { ok: false, status: 400, reason: "invalid_frequency_order" };
    }
  }
  if (preferences.double_sessions != null && !["avoid","sometimes","normal"].includes(preferences.double_sessions)) {
    return { ok: false, status: 400, reason: "invalid_double_sessions" };
  }
  if (preferences.rest_days != null && !["fixed","prefer_one","load_driven","none_required"].includes(preferences.rest_days)) {
    return { ok: false, status: 400, reason: "invalid_rest_days" };
  }
  if (preferences.facilities != null) {
    if (!Array.isArray(preferences.facilities) || preferences.facilities.length > 20 ||
        preferences.facilities.some((value) => typeof value !== "string" || value.length > 64)) {
      return { ok: false, status: 400, reason: "invalid_facilities" };
    }
  }
  for (const key of ["likes", "dislikes"]) {
    if (preferences[key] != null && (typeof preferences[key] !== "string" || preferences[key].length > 800)) {
      return { ok: false, status: 400, reason: "invalid_preferences_text" };
    }
  }

  const constraints = payload.constraints ?? {};
  if (!constraints || typeof constraints !== "object" || Array.isArray(constraints)) {
    return { ok: false, status: 400, reason: "invalid_constraints" };
  }
  const constraintKeys = new Set(["fixed_commitments","other"]);
  if (Object.keys(constraints).some((key) => !constraintKeys.has(key))) {
    return { ok: false, status: 400, reason: "invalid_constraints" };
  }
  for (const key of constraintKeys) {
    if (constraints[key] != null && (typeof constraints[key] !== "string" || constraints[key].length > 1200)) {
      return { ok: false, status: 400, reason: "invalid_constraints" };
    }
  }

  if (!["propose","week_auto","full_within_constraints"].includes(payload.coach_autonomy)) {
    return { ok: false, status: 400, reason: "invalid_coach_autonomy" };
  }
  if (payload.status === "complete") {
    if (goals.length < 1) return { ok: false, status: 400, reason: "goal_required" };
    if (!frequencyValues.every((value) => Number.isInteger(value))) {
      return { ok: false, status: 400, reason: "frequency_required" };
    }
  }

  return {
    ok: true,
    profile: {
      schema_version: 1,
      status: payload.status,
      current_step: payload.current_step,
      goals,
      availability,
      preferences: {
        frequency,
        double_sessions: preferences.double_sessions || null,
        rest_days: preferences.rest_days || null,
        facilities: Array.from(new Set(preferences.facilities || [])),
        likes: String(preferences.likes || "").trim(),
        dislikes: String(preferences.dislikes || "").trim(),
      },
      constraints: {
        fixed_commitments: String(constraints.fixed_commitments || "").trim(),
        other: String(constraints.other || "").trim(),
      },
      coach_autonomy: payload.coach_autonomy,
    },
  };
}

async function supabaseRpc(path, body, env, fetchImpl = fetch) {
  const secretKey = supabaseSecretKey(env);
  if (!configured(secretKey)) throw new Error("Supabase secret key is not configured");
  const projectUrl = configured(env.SUPABASE_PROJECT_URL)
    ? env.SUPABASE_PROJECT_URL.trim().replace(/\/$/, "")
    : DEFAULT_SUPABASE_PROJECT_URL;
  const timeoutMs = Number(env.SUPABASE_TIMEOUT_MS || DEFAULT_SUPABASE_TIMEOUT_MS);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("supabase_profile_timeout"), timeoutMs);
  try {
    const response = await fetchImpl(projectUrl + path, {
      method: "POST",
      signal: controller.signal,
      headers: {
        apikey: secretKey,
        "content-type": "application/json",
        "user-agent": "hall-se-athlete-profile-worker",
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const responseBody = (await response.text()).slice(0, 500);
      throw new Error(`Supabase profile RPC failed: HTTP ${response.status} ${responseBody}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

export function validateAthleteStartingState(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, status: 400, reason: "invalid_starting_state" };
  }
  const allowed = new Set(["schema_version","status","source_mode","manual_state","confirmation"]);
  if (Object.keys(payload).some((key) => !allowed.has(key))) {
    return { ok: false, status: 400, reason: "unexpected_starting_state_fields" };
  }
  if (payload.schema_version !== 1) {
    return { ok: false, status: 400, reason: "invalid_starting_state_version" };
  }
  if (!["draft","confirmed"].includes(payload.status)) {
    return { ok: false, status: 400, reason: "invalid_starting_state_status" };
  }
  if (!["observed","manual","hybrid"].includes(payload.source_mode)) {
    return { ok: false, status: 400, reason: "invalid_starting_state_source" };
  }

  const manual = payload.manual_state ?? {};
  if (!manual || typeof manual !== "object" || Array.isArray(manual)) {
    return { ok: false, status: 400, reason: "invalid_manual_starting_state" };
  }
  const manualKeys = new Set(["training_background","current_days_per_week","disciplines","notes"]);
  if (Object.keys(manual).some((key) => !manualKeys.has(key))) {
    return { ok: false, status: 400, reason: "invalid_manual_starting_state" };
  }
  if (manual.training_background != null &&
      !["new","some","experienced"].includes(manual.training_background)) {
    return { ok: false, status: 400, reason: "invalid_training_background" };
  }
  if (manual.current_days_per_week != null &&
      (!Number.isInteger(manual.current_days_per_week) || manual.current_days_per_week < 0 || manual.current_days_per_week > 7)) {
    return { ok: false, status: 400, reason: "invalid_current_training_days" };
  }
  if (manual.notes != null && (typeof manual.notes !== "string" || manual.notes.length > 1200)) {
    return { ok: false, status: 400, reason: "invalid_starting_state_notes" };
  }

  const disciplines = manual.disciplines ?? {};
  if (!disciplines || typeof disciplines !== "object" || Array.isArray(disciplines)) {
    return { ok: false, status: 400, reason: "invalid_starting_disciplines" };
  }
  const allowedDisciplines = new Set(["run","swim","bike","mtb","strength","other"]);
  for (const [key, value] of Object.entries(disciplines)) {
    if (!allowedDisciplines.has(key) || !value || typeof value !== "object" || Array.isArray(value)) {
      return { ok: false, status: 400, reason: "invalid_starting_discipline" };
    }
    const allowedFields = new Set([
      "sessions_per_week","weekly_distance_km","typical_duration_minutes","long_run_minutes",
      "typical_distance_m","pool_length_m","ftp_w","recent_result","level","notes"
    ]);
    if (Object.keys(value).some((field) => !allowedFields.has(field))) {
      return { ok: false, status: 400, reason: "invalid_starting_discipline_field" };
    }
    for (const field of ["sessions_per_week","weekly_distance_km","typical_duration_minutes","long_run_minutes","typical_distance_m","pool_length_m","ftp_w"]) {
      if (value[field] != null && (typeof value[field] !== "number" || !Number.isFinite(value[field]) || value[field] < 0 || value[field] > 100000)) {
        return { ok: false, status: 400, reason: "invalid_starting_discipline_value" };
      }
    }
    for (const field of ["recent_result","level","notes"]) {
      if (value[field] != null && (typeof value[field] !== "string" || value[field].length > 600)) {
        return { ok: false, status: 400, reason: "invalid_starting_discipline_text" };
      }
    }
  }

  const confirmation = payload.confirmation ?? {};
  if (!confirmation || typeof confirmation !== "object" || Array.isArray(confirmation)) {
    return { ok: false, status: 400, reason: "invalid_starting_confirmation" };
  }
  const confirmationKeys = new Set(["observed_representative","notes"]);
  if (Object.keys(confirmation).some((key) => !confirmationKeys.has(key))) {
    return { ok: false, status: 400, reason: "invalid_starting_confirmation" };
  }
  if (confirmation.observed_representative != null && typeof confirmation.observed_representative !== "boolean") {
    return { ok: false, status: 400, reason: "invalid_observed_confirmation" };
  }
  if (confirmation.notes != null && (typeof confirmation.notes !== "string" || confirmation.notes.length > 800)) {
    return { ok: false, status: 400, reason: "invalid_starting_confirmation_notes" };
  }

  if (payload.status === "confirmed") {
    if (payload.source_mode === "observed" && confirmation.observed_representative !== true) {
      return { ok: false, status: 400, reason: "observed_confirmation_required" };
    }
    if (payload.source_mode === "manual" && Object.keys(disciplines).length === 0 &&
        manual.current_days_per_week == null && !String(manual.notes || "").trim()) {
      return { ok: false, status: 400, reason: "manual_starting_state_required" };
    }
  }

  return {
    ok: true,
    startingState: {
      schema_version: 1,
      status: payload.status,
      source_mode: payload.source_mode,
      manual_state: {
        training_background: manual.training_background || null,
        current_days_per_week: manual.current_days_per_week ?? null,
        disciplines,
        notes: String(manual.notes || "").trim(),
      },
      confirmation: {
        observed_representative: confirmation.observed_representative === true,
        notes: String(confirmation.notes || "").trim(),
      },
    },
  };
}

async function handleAthleteStartingStateRequest(request, env, fetchImpl) {
  const url = new URL(request.url);
  const allowedHost = configured(env.TRAINING_INPUT_HOST)
    ? env.TRAINING_INPUT_HOST.trim().toLowerCase()
    : DEFAULT_TRAINING_INPUT_HOST;
  if (url.hostname.toLowerCase() !== allowedHost) return jsonResponse({ error: "not_found" }, 404);
  if (!accessAssertion(request)) return jsonResponse({ error: "access_required" }, 401);

  const athleteSubject = await athleteSubjectFromRequest(request);
  if (!athleteSubject) return jsonResponse({ error: "access_identity_required" }, 401);

  if (request.method === "GET") {
    try {
      const result = await supabaseRpc(
        ATHLETE_STARTING_STATE_GET_RPC_PATH,
        { p_athlete_subject: athleteSubject },
        env,
        fetchImpl,
      );
      return jsonResponse(result);
    } catch (error) {
      console.error("ATHLETE_STARTING_STATE_READ_FAILED", String(error));
      return jsonResponse({ error: "starting_state_read_failed" }, 503);
    }
  }

  if (request.method !== "PUT") return jsonResponse({ error: "method_not_allowed" }, 405);

  let raw;
  try {
    raw = await request.text();
  } catch {
    return jsonResponse({ error: "invalid_body" }, 400);
  }
  if (raw.length > 32768) return jsonResponse({ error: "payload_too_large" }, 413);

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  const validation = validateAthleteStartingState(payload);
  if (!validation.ok) return jsonResponse({ error: validation.reason }, validation.status);

  try {
    const result = await supabaseRpc(
      ATHLETE_STARTING_STATE_UPSERT_RPC_PATH,
      {
        p_athlete_subject: athleteSubject,
        p_state: validation.startingState,
      },
      env,
      fetchImpl,
    );
    return jsonResponse(result);
  } catch (error) {
    console.error("ATHLETE_STARTING_STATE_SAVE_FAILED", String(error));
    return jsonResponse({ error: "starting_state_save_failed" }, 503);
  }
}

async function handleAthleteProfileRequest(request, env, fetchImpl, executionContext = null) {
  const url = new URL(request.url);
  const allowedHost = configured(env.TRAINING_INPUT_HOST)
    ? env.TRAINING_INPUT_HOST.trim().toLowerCase()
    : DEFAULT_TRAINING_INPUT_HOST;
  if (url.hostname.toLowerCase() !== allowedHost) return jsonResponse({ error: "not_found" }, 404);
  if (!accessAssertion(request)) return jsonResponse({ error: "access_required" }, 401);

  const athleteSubject = await athleteSubjectFromRequest(request);
  if (!athleteSubject) return jsonResponse({ error: "access_identity_required" }, 401);

  if (request.method === "GET") {
    try {
      const result = await supabaseRpc(
        ATHLETE_PROFILE_GET_RPC_PATH,
        { p_athlete_subject: athleteSubject },
        env,
        fetchImpl,
      );
      return jsonResponse(result);
    } catch (error) {
      console.error("ATHLETE_PROFILE_READ_FAILED", String(error));
      return jsonResponse({ error: "profile_read_failed" }, 503);
    }
  }

  if (request.method !== "PUT") return jsonResponse({ error: "method_not_allowed" }, 405);

  let raw;
  try {
    raw = await request.text();
  } catch {
    return jsonResponse({ error: "invalid_body" }, 400);
  }
  if (raw.length > 32768) return jsonResponse({ error: "payload_too_large" }, 413);

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  const validation = validateAthleteProfile(payload);
  if (!validation.ok) return jsonResponse({ error: validation.reason }, validation.status);

  let result;
  try {
    result = await supabaseRpc(
      ATHLETE_PROFILE_UPSERT_RPC_PATH,
      {
        p_athlete_subject: athleteSubject,
        p_profile: validation.profile,
        // Browser onboarding is per athlete. It must never promote a user to the
        // legacy single-athlete planning_default bridge.
        p_set_planning_default: false,
      },
      env,
      fetchImpl,
    );
  } catch (error) {
    console.error("ATHLETE_PROFILE_SAVE_FAILED", String(error));
    return jsonResponse({ error: "profile_save_failed" }, 503);
  }

  if (validation.profile.status !== "complete") {
    return jsonResponse({ ...result, processing: "draft_saved" });
  }

  // Completion is deliberately only a durable profile write in v1. The coach
  // must not reinterpret goals or replan until the declared-profile planning
  // contract is connected and verified end-to-end.
  return jsonResponse({ ...result, processing: "profile_saved" });
}

function validUuid(value) {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

async function handleAthletePlanGenerationRequest(request, env, fetchImpl) {
  const url = new URL(request.url);
  const allowedHost = configured(env.TRAINING_INPUT_HOST)
    ? env.TRAINING_INPUT_HOST.trim().toLowerCase()
    : DEFAULT_TRAINING_INPUT_HOST;
  if (url.hostname.toLowerCase() !== allowedHost) return jsonResponse({ error: "not_found" }, 404);
  if (!accessAssertion(request)) return jsonResponse({ error: "access_required" }, 401);

  const athleteSubject = await athleteSubjectFromRequest(request);
  if (!athleteSubject) return jsonResponse({ error: "access_identity_required" }, 401);

  if (request.method === "GET") {
    const requestId = String(url.searchParams.get("id") || "").trim();
    if (!validUuid(requestId)) return jsonResponse({ error: "invalid_request_id" }, 400);
    try {
      const result = await supabaseRpc(
        ATHLETE_PLAN_GET_RPC_PATH,
        { p_athlete_subject: athleteSubject, p_request_id: requestId },
        env,
        fetchImpl,
      );
      return jsonResponse(result);
    } catch (error) {
      console.error("ATHLETE_PLAN_STATUS_FAILED", String(error));
      return jsonResponse({ error: "generation_status_failed" }, 503);
    }
  }

  if (request.method !== "POST") return jsonResponse({ error: "method_not_allowed" }, 405);

  let generation;
  try {
    generation = await supabaseRpc(
      ATHLETE_PLAN_REQUEST_RPC_PATH,
      { p_athlete_subject: athleteSubject },
      env,
      fetchImpl,
    );
  } catch (error) {
    console.error("ATHLETE_PLAN_REQUEST_FAILED", String(error));
    return jsonResponse({ error: "plan_request_failed" }, 503);
  }

  const requestId = String(generation?.request_id || "");
  if (!validUuid(requestId)) {
    console.error("ATHLETE_PLAN_REQUEST_INVALID_ACK", JSON.stringify(generation || {}));
    return jsonResponse({ error: "plan_request_invalid_ack" }, 503);
  }

  if (generation.created !== true) {
    return jsonResponse({
      status: generation.status,
      request_id: requestId,
      profile_revision: generation.profile_revision,
      starting_state_revision: generation.starting_state_revision,
      processing: generation.status === "running" ? "running" : "queued",
    });
  }

  const event = {
    request_id: requestId,
    profile_revision: generation.profile_revision,
    starting_state_revision: generation.starting_state_revision,
    event_key: "athlete-plan:" + requestId,
    source: "athlete-profile-v1",
  };
  const eventType = configured(env.ATHLETE_PLAN_EVENT_TYPE)
    ? env.ATHLETE_PLAN_EVENT_TYPE.trim()
    : DEFAULT_ATHLETE_PLAN_EVENT_TYPE;

  try {
    await dispatchToGitHub(event, env, fetchImpl, eventType);
  } catch (error) {
    console.error("ATHLETE_PLAN_DISPATCH_FAILED", requestId, String(error));
    try {
      await supabaseRpc(
        ATHLETE_PLAN_STATUS_RPC_PATH,
        {
          p_request_id: requestId,
          p_status: "failed",
          p_error: "dispatch_failed",
          p_result_week_key: null,
        },
        env,
        fetchImpl,
      );
    } catch (statusError) {
      console.error("ATHLETE_PLAN_FAILURE_STATUS_FAILED", requestId, String(statusError));
    }
    return jsonResponse({ error: "plan_dispatch_failed", request_id: requestId }, 503);
  }

  return jsonResponse({
    status: "queued",
    request_id: requestId,
    profile_revision: generation.profile_revision,
    starting_state_revision: generation.starting_state_revision,
    processing: "queued",
  });
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function webhookPathTokenFromSecret(secret) {
  if (!configured(secret)) return null;
  return (await sha256Hex(secret.trim())).slice(0, 32);
}

async function secretFingerprint(secret) {
  if (!configured(secret)) return null;
  return (await sha256Hex(secret.trim())).slice(0, 12);
}

async function expectedWebhookPath(env) {
  const token = await webhookPathTokenFromSecret(env.WEBHOOK_PATH_SECRET);
  return token ? `/strava/${token}` : null;
}

function integerString(value) {
  return Number.isInteger(value) ? String(value) : "";
}

export function validateActivityEvent(payload, env) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, status: 400, reason: "invalid_payload" };
  }
  if (payload.object_type !== "activity") {
    return { ok: true, ignored: true, reason: "non_activity_event" };
  }
  if (!["create", "update", "delete"].includes(payload.aspect_type)) {
    return { ok: false, status: 400, reason: "invalid_aspect_type" };
  }
  const objectId = integerString(payload.object_id);
  const ownerId = integerString(payload.owner_id);
  const subscriptionId = integerString(payload.subscription_id);
  const eventTime = integerString(payload.event_time);
  if (!objectId || !ownerId || !subscriptionId || !eventTime) {
    return { ok: false, status: 400, reason: "invalid_event_identifiers" };
  }
  if (!configured(env.STRAVA_OWNER_ID) || !configured(env.STRAVA_SUBSCRIPTION_ID)) {
    return { ok: false, status: 503, reason: "webhook_identity_not_configured" };
  }
  if (ownerId !== env.STRAVA_OWNER_ID.trim()) {
    return { ok: false, status: 403, reason: "owner_mismatch" };
  }
  if (subscriptionId !== env.STRAVA_SUBSCRIPTION_ID.trim()) {
    return { ok: false, status: 403, reason: "subscription_mismatch" };
  }

  const eventKey = `${subscriptionId}:activity:${objectId}:${payload.aspect_type}:${eventTime}`;
  return {
    ok: true,
    event: {
      object_type: "activity",
      object_id: Number(objectId),
      aspect_type: payload.aspect_type,
      owner_id: Number(ownerId),
      subscription_id: Number(subscriptionId),
      event_time: Number(eventTime),
      event_key: eventKey,
      updates: payload.updates && typeof payload.updates === "object" ? payload.updates : {},
    },
  };
}

export async function persistTrainingInput(event, env, fetchImpl = fetch) {
  const secretKey = supabaseSecretKey(env);
  if (!configured(secretKey)) {
    throw new Error("Supabase secret key is not configured");
  }
  const projectUrl = configured(env.SUPABASE_PROJECT_URL)
    ? env.SUPABASE_PROJECT_URL.trim().replace(/\/$/, "")
    : DEFAULT_SUPABASE_PROJECT_URL;
  const timeoutMs = Number(env.SUPABASE_TIMEOUT_MS || DEFAULT_SUPABASE_TIMEOUT_MS);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("supabase_feedback_timeout"), timeoutMs);

  try {
    const response = await fetchImpl(projectUrl + TRAINING_FEEDBACK_RPC_PATH, {
      method: "POST",
      signal: controller.signal,
      headers: {
        apikey: secretKey,
        "content-type": "application/json",
        "user-agent": "hall-se-training-input-worker",
      },
      body: JSON.stringify({
        p_provider_activity_id: String(event.activity_id),
        p_source: event.source,
        p_operation: event.operation,
        p_feedback_text: event.text,
        p_rpe: event.rpe,
        p_feeling: event.feeling,
        p_event_key: event.event_key,
        p_submitted_at: event.submitted_at,
        p_raw: event,
      }),
    });
    if (!response.ok) {
      const body = (await response.text()).slice(0, 500);
      throw new Error(`Supabase feedback RPC failed: HTTP ${response.status} ${body}`);
    }
    const body = await response.json().catch(() => ({}));
    if (body?.status !== "saved" || body?.event_key !== event.event_key) {
      throw new Error("Supabase feedback RPC returned an invalid acknowledgement");
    }
    return body;
  } finally {
    clearTimeout(timer);
  }
}


export async function dispatchToGitHub(event, env, fetchImpl = fetch, eventTypeOverride = null) {
  if (!configured(env.GITHUB_DISPATCH_TOKEN)) {
    throw new Error("GITHUB_DISPATCH_TOKEN is not configured");
  }
  const repository = configured(env.GITHUB_REPOSITORY)
    ? env.GITHUB_REPOSITORY.trim()
    : DEFAULT_REPOSITORY;
  if (!/^[^/]+\/[^/]+$/.test(repository)) {
    throw new Error("GITHUB_REPOSITORY must be owner/repo");
  }
  const eventType = configured(eventTypeOverride)
    ? eventTypeOverride.trim()
    : configured(env.DISPATCH_EVENT_TYPE)
      ? env.DISPATCH_EVENT_TYPE.trim()
      : DEFAULT_EVENT_TYPE;
  const apiVersion = configured(env.GITHUB_API_VERSION)
    ? env.GITHUB_API_VERSION.trim()
    : DEFAULT_GITHUB_API_VERSION;
  const timeoutMs = Number(env.DISPATCH_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("github_dispatch_timeout"), timeoutMs);

  try {
    const response = await fetchImpl(`https://api.github.com/repos/${repository}/dispatches`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        "content-type": "application/json",
        "user-agent": "hall-se-strava-webhook",
        "x-github-api-version": apiVersion,
      },
      body: JSON.stringify({
        event_type: eventType,
        client_payload: event,
      }),
    });
    if (response.status !== 204) {
      const body = (await response.text()).slice(0, 500);
      throw new Error(`GitHub repository_dispatch failed: HTTP ${response.status} ${body}`);
    }
  } finally {
    clearTimeout(timer);
  }
}


export function validateTrainingInput(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, status: 400, reason: "invalid_payload" };
  }
  const allowed = new Set(["operation", "activity_id", "text", "rpe", "feeling", "source"]);
  const extra = Object.keys(payload).filter((key) => !allowed.has(key));
  if (extra.length) return { ok: false, status: 400, reason: "unexpected_fields" };

  const operation = typeof payload.operation === "string" ? payload.operation.trim().toUpperCase() : "";
  if (!TRAINING_INPUT_OPERATIONS.has(operation)) {
    return { ok: false, status: 400, reason: "invalid_operation" };
  }
  if (!Number.isInteger(payload.activity_id) || payload.activity_id <= 0) {
    return { ok: false, status: 400, reason: "invalid_activity_id" };
  }

  const text = payload.text == null ? "" : payload.text;
  if (typeof text !== "string" || text.length > 800) {
    return { ok: false, status: 400, reason: "invalid_text" };
  }
  const normalizedText = text.trim();

  const rpe = payload.rpe == null ? null : payload.rpe;
  if (rpe !== null && (!Number.isInteger(rpe) || rpe < 1 || rpe > 10)) {
    return { ok: false, status: 400, reason: "invalid_rpe" };
  }

  const feeling = payload.feeling == null ? [] : payload.feeling;
  if (!Array.isArray(feeling) || feeling.length > 1) {
    return { ok: false, status: 400, reason: "invalid_feeling" };
  }
  const normalizedFeeling = [];
  for (const value of feeling) {
    if (typeof value !== "string" || !TRAINING_INPUT_FEELINGS.has(value)) {
      return { ok: false, status: 400, reason: "invalid_feeling" };
    }
    if (!normalizedFeeling.includes(value)) normalizedFeeling.push(value);
  }

  const source = payload.source == null ? "training-gui" : payload.source;
  if (typeof source !== "string" || source.length > 64) {
    return { ok: false, status: 400, reason: "invalid_source" };
  }
  if (!normalizedText && rpe === null && normalizedFeeling.length === 0) {
    return { ok: false, status: 400, reason: "empty_input" };
  }

  return {
    ok: true,
    input: {
      operation,
      activity_id: payload.activity_id,
      text: normalizedText,
      rpe,
      feeling: normalizedFeeling,
      source: source.trim() || "training-gui",
    },
  };
}

async function handleTrainingInputRequest(request, env, fetchImpl, executionContext = null) {
  const url = new URL(request.url);
  const allowedHost = configured(env.TRAINING_INPUT_HOST)
    ? env.TRAINING_INPUT_HOST.trim().toLowerCase()
    : DEFAULT_TRAINING_INPUT_HOST;
  if (url.hostname.toLowerCase() !== allowedHost) {
    return jsonResponse({ error: "not_found" }, 404);
  }
  if (request.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }
  if (!configured(request.headers.get("cf-access-jwt-assertion"))) {
    return jsonResponse({ error: "access_required" }, 401);
  }

  let raw;
  try {
    raw = await request.text();
  } catch {
    return jsonResponse({ error: "invalid_body" }, 400);
  }
  if (raw.length > 4096) {
    return jsonResponse({ error: "payload_too_large" }, 413);
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }

  const validation = validateTrainingInput(payload);
  if (!validation.ok) {
    console.warn("TRAINING_INPUT_REJECTED", validation.reason);
    return jsonResponse({ error: validation.reason }, validation.status);
  }

  const submittedAt = new Date().toISOString();
  const digest = await sha256Hex(JSON.stringify(validation.input) + ":" + submittedAt);
  const event = {
    ...validation.input,
    submitted_at: submittedAt,
    event_key: "training-input:" + digest.slice(0, 24),
  };

  const directPersistence = directTrainingInputPersistenceConfigured(env);
  if (!directPersistence) {
    console.error("TRAINING_INPUT_PERSISTENCE_NOT_CONFIGURED", event.operation);
    return jsonResponse({ error: "persistence_not_configured" }, 503);
  }
  try {
    await persistTrainingInput(event, env, fetchImpl);
    console.log("TRAINING_INPUT_PERSISTED", event.event_key, event.operation);
  } catch (error) {
    console.error("TRAINING_INPUT_PERSIST_FAILED", event.event_key, String(error));
    return jsonResponse({ error: "persistence_failed" }, 503);
  }

  const eventType = configured(env.TRAINING_INPUT_EVENT_TYPE)
    ? env.TRAINING_INPUT_EVENT_TYPE.trim()
    : DEFAULT_TRAINING_INPUT_EVENT_TYPE;
  const dispatch = async () => {
    try {
      await dispatchToGitHub(event, env, fetchImpl, eventType);
      console.log("TRAINING_INPUT_DISPATCHED", event.event_key, event.operation);
    } catch (error) {
      console.error("TRAINING_INPUT_DISPATCH_FAILED", event.event_key, String(error));
      throw error;
    }
  };

  if (executionContext && typeof executionContext.waitUntil === "function") {
    executionContext.waitUntil(
      dispatch().catch(() => {
        // The feedback is already durable in Supabase. A later scheduled
        // canonical run hydrates it even if this best-effort dispatch fails.
      }),
    );
    return jsonResponse({
      status: "saved",
      persistence: "supabase",
      processing: "queued",
      event_key: event.event_key,
    });
  }

  try {
    await dispatch();
  } catch {
    return jsonResponse({
      status: "saved",
      persistence: "supabase",
      processing: "deferred",
      event_key: event.event_key,
    }, 202);
  }

  return jsonResponse({
    status: "saved",
    persistence: "supabase",
    processing: "queued",
    event_key: event.event_key,
  });
}

export async function handleRequest(request, env, fetchImpl = fetch, executionContext = null) {
  const url = new URL(request.url);

  if (url.pathname === "/healthz") {
    return jsonResponse({
      ok: true,
      webhook_path_configured: configured(env.WEBHOOK_PATH_SECRET),
      verify_token_configured: configured(env.STRAVA_VERIFY_TOKEN),
      owner_configured: configured(env.STRAVA_OWNER_ID),
      subscription_configured: configured(env.STRAVA_SUBSCRIPTION_ID),
      github_dispatch_configured: configured(env.GITHUB_DISPATCH_TOKEN),
      training_input_direct_persistence_configured: directTrainingInputPersistenceConfigured(env),
      training_input_endpoint: TRAINING_INPUT_PATH,
      athlete_profile_endpoint: ATHLETE_PROFILE_PATH,
      athlete_starting_state_endpoint: ATHLETE_STARTING_STATE_PATH,
      athlete_plan_generation_endpoint: ATHLETE_PLAN_GENERATE_PATH,
      webhook_path_fingerprint: await secretFingerprint(env.WEBHOOK_PATH_SECRET),
      verify_token_fingerprint: await secretFingerprint(env.STRAVA_VERIFY_TOKEN),
    });
  }

  if (decodeURIComponent(url.pathname) === TRAINING_INPUT_PATH) {
    return handleTrainingInputRequest(request, env, fetchImpl, executionContext);
  }
  if (decodeURIComponent(url.pathname) === ATHLETE_PROFILE_PATH) {
    return handleAthleteProfileRequest(request, env, fetchImpl, executionContext);
  }
  if (decodeURIComponent(url.pathname) === ATHLETE_STARTING_STATE_PATH) {
    return handleAthleteStartingStateRequest(request, env, fetchImpl);
  }
  if (decodeURIComponent(url.pathname) === ATHLETE_PLAN_GENERATE_PATH) {
    return handleAthletePlanGenerationRequest(request, env, fetchImpl);
  }

  const webhookPath = await expectedWebhookPath(env);
  if (!webhookPath) return jsonResponse({ error: "webhook_path_not_configured" }, 503);
  if (url.pathname !== webhookPath) return jsonResponse({ error: "not_found" }, 404);

  if (request.method === "GET") {
    const mode = url.searchParams.get("hub.mode") || "";
    const challenge = url.searchParams.get("hub.challenge") || "";
    const token = url.searchParams.get("hub.verify_token") || "";
    if (
      mode !== "subscribe" ||
      !challenge ||
      !configured(env.STRAVA_VERIFY_TOKEN) ||
      token !== env.STRAVA_VERIFY_TOKEN
    ) {
      return jsonResponse({ error: "verification_failed" }, 403);
    }
    return jsonResponse({ "hub.challenge": challenge });
  }

  if (request.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }

  const validation = validateActivityEvent(payload, env);
  if (!validation.ok) {
    console.warn("STRAVA_WEBHOOK_REJECTED", validation.reason);
    return jsonResponse({ error: validation.reason }, validation.status);
  }
  if (validation.ignored) {
    console.log("STRAVA_WEBHOOK_IGNORED", validation.reason);
    return jsonResponse({ status: "ignored" });
  }

  try {
    await dispatchToGitHub(validation.event, env, fetchImpl);
  } catch (error) {
    console.error("STRAVA_DISPATCH_FAILED", validation.event.event_key, String(error));
    return jsonResponse({ error: "dispatch_failed" }, 503);
  }

  console.log("STRAVA_DISPATCHED", validation.event.event_key);
  return jsonResponse({ status: "accepted", event_key: validation.event.event_key });
}

export default {
  async fetch(request, env, ctx) {
    return handleRequest(request, env, fetch, ctx);
  },
};
