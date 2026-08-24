import test from "node:test";
import assert from "node:assert/strict";

import { handleRequest } from "../src/worker.mjs";

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

test("Strava subscription verification echoes challenge", async () => {
  const request = new Request(
    "https://hooks.example/strava/path-secret?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=verify-secret",
  );
  const response = await handleRequest(request, env, async () => {
    throw new Error("GitHub must not be called during verification");
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { "hub.challenge": "abc" });
});

test("wrong verification token is rejected", async () => {
  const request = new Request(
    "https://hooks.example/strava/path-secret?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=wrong",
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
  const request = new Request("https://hooks.example/strava/path-secret", {
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
  const request = new Request("https://hooks.example/strava/path-secret", {
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
  const request = new Request("https://hooks.example/strava/path-secret", {
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
  const request = new Request("https://hooks.example/strava/path-secret", {
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
