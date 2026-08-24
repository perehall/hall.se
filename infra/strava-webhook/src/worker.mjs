const DEFAULT_REPOSITORY = "perehall/hall.se";
const DEFAULT_EVENT_TYPE = "strava-activity-event";
const DEFAULT_GITHUB_API_VERSION = "2026-03-10";
const DEFAULT_TIMEOUT_MS = 1500;

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

export async function webhookPathTokenFromSecret(secret) {
  if (!configured(secret)) return null;
  const bytes = new TextEncoder().encode(secret.trim());
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
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

export async function dispatchToGitHub(event, env, fetchImpl = fetch) {
  if (!configured(env.GITHUB_DISPATCH_TOKEN)) {
    throw new Error("GITHUB_DISPATCH_TOKEN is not configured");
  }
  const repository = configured(env.GITHUB_REPOSITORY)
    ? env.GITHUB_REPOSITORY.trim()
    : DEFAULT_REPOSITORY;
  if (!/^[^/]+\/[^/]+$/.test(repository)) {
    throw new Error("GITHUB_REPOSITORY must be owner/repo");
  }
  const eventType = configured(env.DISPATCH_EVENT_TYPE)
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

export async function handleRequest(request, env, fetchImpl = fetch) {
  const url = new URL(request.url);

  if (url.pathname === "/healthz") {
    return jsonResponse({
      ok: true,
      webhook_path_configured: configured(env.WEBHOOK_PATH_SECRET),
      verify_token_configured: configured(env.STRAVA_VERIFY_TOKEN),
      owner_configured: configured(env.STRAVA_OWNER_ID),
      subscription_configured: configured(env.STRAVA_SUBSCRIPTION_ID),
      github_dispatch_configured: configured(env.GITHUB_DISPATCH_TOKEN),
    });
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
  async fetch(request, env) {
    return handleRequest(request, env);
  },
};
