import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { handleRequest, webhookPathTokenFromSecret } from "../src/worker.mjs";

const env = {
  WEBHOOK_PATH_SECRET: "path-secret",
  STRAVA_VERIFY_TOKEN: "verify-secret",
  STRAVA_OWNER_ID: "123",
  STRAVA_SUBSCRIPTION_ID: "456",
  GITHUB_DISPATCH_TOKEN: "github-secret",
  GITHUB_REPOSITORY: "perehall/hall.se",
  DISPATCH_EVENT_TYPE: "strava-activity-event",
  GITHUB_API_VERSION: "2026-03-10",
  DISPATCH_TIMEOUT_MS: "1500",
  SUPABASE_PROJECT_URL: "https://example.supabase.co",
  SUPABASE_SECRET_KEY: "sb_secret_test",
  SUPABASE_TIMEOUT_MS: "1500",
};

function event(overrides = {}) {
  return {
    object_type: "activity",
    object_id: 789,
    aspect_type: "create",
    owner_id: 123,
    subscription_id: 456,
    event_time: 1000,
    updates: {},
    ...overrides,
  };
}

async function webhookUrl(query = "") {
  const token = await webhookPathTokenFromSecret(env.WEBHOOK_PATH_SECRET);
  return `https://hooks.example/strava/${token}${query}`;
}

test("webhook path token is deterministic and URL-safe", async () => {
  const first = await webhookPathTokenFromSecret(" path-secret ");
  const second = await webhookPathTokenFromSecret("path-secret");
  assert.equal(first, second);
  assert.match(first, /^[0-9a-f]{32}$/);
});

test("Strava subscription verification echoes challenge", async () => {
  const request = new Request(
    await webhookUrl("?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=verify-secret"),
  );
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called during verification");
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { "hub.challenge": "abc" });
});

test("wrong verification token is rejected", async () => {
  const request = new Request(
    await webhookUrl("?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=wrong"),
  );
  const response = await handleRequest(request, env);
  assert.equal(response.status, 403);
});

test("valid activity event dispatches exact repository event", async () => {
  let requestBody;
  let authHeader;
  const fakeFetch = async (url, init) => {
    assert.equal(url, "https://api.github.com/repos/perehall/hall.se/dispatches");
    authHeader = init.headers.authorization;
    requestBody = JSON.parse(init.body);
    return new Response(null, { status: 204 });
  };
  const request = new Request(await webhookUrl(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(event()),
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  assert.equal(authHeader, "Bearer github-secret");
  assert.equal(requestBody.event_type, "strava-activity-event");
  assert.equal(requestBody.client_payload.object_id, 789);
  assert.equal(requestBody.client_payload.event_key, "456:activity:789:create:1000");
});

test("owner and subscription are enforced", async () => {
  const request = new Request(await webhookUrl(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(event({ owner_id: 999 })),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called for rejected event");
  });
  assert.equal(response.status, 403);
});

test("GitHub failure returns non-200 so Strava can retry", async () => {
  const request = new Request(await webhookUrl(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(event()),
  });
  const response = await handleRequest(
    request,
    env,
    async () => new Response("temporary failure", { status: 503 }),
  );
  assert.equal(response.status, 503);
});

test("athlete events are acknowledged without dispatch", async () => {
  const request = new Request(await webhookUrl(), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(event({ object_type: "athlete" })),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called for athlete events");
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ignored" });
});


test("authenticated training GUI input is persisted before async dispatch", async () => {
  let persistBody;
  let dispatchBody;
  const calls = [];
  const fakeFetch = async (url, init) => {
    calls.push(url);
    if (url === "https://example.supabase.co/rest/v1/rpc/training_submit_activity_feedback") {
      assert.equal(init.headers.apikey, "sb_secret_test");
      persistBody = JSON.parse(init.body);
      return new Response(JSON.stringify({
        status: "saved",
        event_key: persistBody.p_event_key,
        feedback_id: "feedback-id",
      }), {
        status: 200,
        headers: {"content-type": "application/json"},
      });
    }
    assert.equal(url, "https://api.github.com/repos/perehall/hall.se/dispatches");
    dispatchBody = JSON.parse(init.body);
    return new Response(null, { status: 204 });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "NATURAL_LANGUAGE",
      activity_id: 789,
      text: "Blev 4 × 8 i stället för 3 × 10. Pigg efteråt.",
      rpe: 6,
      feeling: ["fresh", "could_do_more"],
      source: "training-gui-v1",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.status, "saved");
  assert.equal(body.persistence, "supabase");
  assert.equal(body.processing, "queued");
  assert.deepEqual(calls, [
    "https://example.supabase.co/rest/v1/rpc/training_submit_activity_feedback",
    "https://api.github.com/repos/perehall/hall.se/dispatches",
  ]);
  assert.equal(persistBody.p_provider_activity_id, "789");
  assert.equal(persistBody.p_operation, "NATURAL_LANGUAGE");
  assert.equal(persistBody.p_rpe, 6);
  assert.deepEqual(persistBody.p_feeling, ["fresh", "could_do_more"]);
  assert.equal(dispatchBody.event_type, "training-input-event");
  assert.equal(dispatchBody.client_payload.activity_id, 789);
  assert.match(dispatchBody.client_payload.event_key, /^training-input:/);
  assert.equal(dispatchBody.client_payload.event_key, persistBody.p_event_key);
});

test("training GUI input fails closed when direct persistence fails", async () => {
  let githubCalled = false;
  const fakeFetch = async (url) => {
    if (url.includes("supabase.co")) {
      return new Response("database unavailable", { status: 503 });
    }
    githubCalled = true;
    return new Response(null, { status: 204 });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      text: "Kontrollerat.",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { error: "persistence_failed" });
  assert.equal(githubCalled, false);
});

test("training GUI input stays saved when async dispatch fails after persistence", async () => {
  const fakeFetch = async (url, init) => {
    if (url.includes("supabase.co")) {
      const body = JSON.parse(init.body);
      return new Response(JSON.stringify({
        status: "saved",
        event_key: body.p_event_key,
      }), {
        status: 200,
        headers: {"content-type": "application/json"},
      });
    }
    return new Response("temporary failure", { status: 503 });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      text: "Kontrollerat.",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch);
  const body = await response.json();
  assert.equal(response.status, 202);
  assert.equal(body.status, "saved");
  assert.equal(body.persistence, "supabase");
  assert.equal(body.processing, "deferred");
});

test("training GUI input keeps dispatch-only fallback until Supabase secret is configured", async () => {
  const fallbackEnv = { ...env };
  delete fallbackEnv.SUPABASE_SECRET_KEY;
  let requestBody;
  const fakeFetch = async (url, init) => {
    assert.equal(url, "https://api.github.com/repos/perehall/hall.se/dispatches");
    requestBody = JSON.parse(init.body);
    return new Response(null, { status: 204 });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      text: "Pigg.",
    }),
  });
  const response = await handleRequest(request, fallbackEnv, fakeFetch);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.status, "accepted");
  assert.equal(body.persistence, "dispatch");
  assert.equal(requestBody.event_type, "training-input-event");
});

test("training GUI input requires Cloudflare Access assertion", async () => {
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      text: "Pigg.",
    }),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called without Access");
  });
  assert.equal(response.status, 401);
});

test("training GUI input rejects operations outside the allowlist", async () => {
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "WRITE_PLAN",
      activity_id: 789,
      text: "Make tomorrow harder.",
    }),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called for invalid operation");
  });
  assert.equal(response.status, 400);
});


test("training GUI input rejects non-custom hostname before request processing", async () => {
  const request = new Request("https://hall-se.per-e-hall.workers.dev/träning/training-api/input", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      text: "Pigg.",
    }),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called from an unapproved hostname");
  });
  assert.equal(response.status, 404);
});


test("Wrangler keeps workers.dev enabled for the registered Strava callback", () => {
  const config = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  assert.match(config, /"workers_dev"\s*:\s*true/);
  assert.match(config, /"name"\s*:\s*"hall-se"/);
});
