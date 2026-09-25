const DEFAULT_REPOSITORY = "perehall/hall.se";
const DEFAULT_EVENT_TYPE = "strava-activity-event";
const DEFAULT_TRAINING_INPUT_EVENT_TYPE = "training-input-event";
const TRAINING_INPUT_PATH = "/träning/training-api/input";
const DEFAULT_TRAINING_INPUT_HOST = "xn--hll-qla.se";
const TRAINING_INPUT_OPERATIONS = new Set(["ADD_FEEDBACK", "UPDATE_COMPLETED_WORKOUT", "ADD_SPONTANEOUS_WORKOUT", "REPORT_PAIN", "REPORT_FATIGUE", "NATURAL_LANGUAGE"]);
const TRAINING_INPUT_FEELINGS = new Set(["fresh", "tired", "strong_legs", "heavy_legs", "pain", "could_do_more"]);
const DEFAULT_GITHUB_API_VERSION = "2026-03-10";
const DEFAULT_TIMEOUT_MS = 1500;
const DEFAULT_SUPABASE_PROJECT_URL = "https://izzevnhgtsvffpkccoai.supabase.co";
const TRAINING_FEEDBACK_RPC_PATH = "/rest/v1/rpc/training_submit_activity_feedback";
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
  if (!Array.isArray(feeling) || feeling.length > 6) {
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
  if (directPersistence) {
    try {
      await persistTrainingInput(event, env, fetchImpl);
      console.log("TRAINING_INPUT_PERSISTED", event.event_key, event.operation);
    } catch (error) {
      console.error("TRAINING_INPUT_PERSIST_FAILED", event.event_key, String(error));
      return jsonResponse({ error: "persistence_failed" }, 503);
    }
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

  if (directPersistence && executionContext && typeof executionContext.waitUntil === "function") {
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
    if (directPersistence) {
      return jsonResponse({
        status: "saved",
        persistence: "supabase",
        processing: "deferred",
        event_key: event.event_key,
      }, 202);
    }
    return jsonResponse({ error: "dispatch_failed" }, 503);
  }

  return jsonResponse({
    status: directPersistence ? "saved" : "accepted",
    persistence: directPersistence ? "supabase" : "dispatch",
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
      webhook_path_fingerprint: await secretFingerprint(env.WEBHOOK_PATH_SECRET),
      verify_token_fingerprint: await secretFingerprint(env.STRAVA_VERIFY_TOKEN),
    });
  }

  if (decodeURIComponent(url.pathname) === TRAINING_INPUT_PATH) {
    return handleTrainingInputRequest(request, env, fetchImpl, executionContext);
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
