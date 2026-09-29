import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { handleRequest, validateAthleteProfile, webhookPathTokenFromSecret } from "../src/worker.mjs";

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


test("authenticated training GUI input returns after persistence without waiting for dispatch", async () => {
  let persistBody;
  let dispatchBody;
  let releaseDispatch;
  const calls = [];
  const background = [];
  const dispatchGate = new Promise((resolve) => { releaseDispatch = resolve; });
  const ctx = {
    waitUntil(promise) {
      background.push(promise);
    },
  };
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
    await dispatchGate;
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
      feeling: ["fresh"],
      source: "training-gui-v1",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch, ctx);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.status, "saved");
  assert.equal(body.persistence, "supabase");
  assert.equal(body.processing, "queued");
  assert.equal(background.length, 1);
  assert.deepEqual(calls, [
    "https://example.supabase.co/rest/v1/rpc/training_submit_activity_feedback",
    "https://api.github.com/repos/perehall/hall.se/dispatches",
  ]);
  assert.equal(persistBody.p_provider_activity_id, "789");
  assert.equal(persistBody.p_operation, "NATURAL_LANGUAGE");
  assert.equal(persistBody.p_rpe, 6);
  assert.deepEqual(persistBody.p_feeling, ["fresh"]);
  assert.equal(dispatchBody.event_type, "training-input-event");
  assert.equal(dispatchBody.client_payload.activity_id, 789);
  assert.match(dispatchBody.client_payload.event_key, /^training-input:/);
  assert.equal(dispatchBody.client_payload.event_key, persistBody.p_event_key);
  releaseDispatch();
  await background[0];
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

test("training GUI input stays saved when background dispatch fails after persistence", async () => {
  const background = [];
  const ctx = {
    waitUntil(promise) {
      background.push(promise);
    },
  };
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
  const response = await handleRequest(request, env, fakeFetch, ctx);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.status, "saved");
  assert.equal(body.persistence, "supabase");
  assert.equal(body.processing, "queued");
  assert.equal(background.length, 1);
  await background[0];
});

test("training GUI input fails closed when durable persistence is not configured", async () => {
  const noPersistenceEnv = { ...env };
  delete noPersistenceEnv.SUPABASE_SECRET_KEY;
  let externalCallMade = false;
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
  const response = await handleRequest(request, noPersistenceEnv, async () => {
    externalCallMade = true;
    throw new Error("No external service may be called without durable persistence");
  });
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { error: "persistence_not_configured" });
  assert.equal(externalCallMade, false);
});

test("training GUI input rejects multiple feelings", async () => {
  const request = new Request("https://xn--hll-qla.se/träning/training-api/input", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
    },
    body: JSON.stringify({
      operation: "ADD_FEEDBACK",
      activity_id: 789,
      rpe: 6,
      feeling: ["fresh", "could_do_more"],
    }),
  });
  const response = await handleRequest(request, env, async () => {
    throw new Error("Rejected input must not call external services");
  });
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { error: "invalid_feeling" });
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


test("athlete profile validation keeps goals and life constraints separate from observed capacity", () => {
  const result = validateAthleteProfile({
    schema_version: 1,
    status: "complete",
    current_step: 8,
    goals: [
      { text: "Bli bättre på MTB och springa starkt.", target_date: null, importance: "equal" },
      { text: "Topp 10 på ett swimrun 2027.", target_date: "2027-08-14", importance: "primary" },
    ],
    availability: {
      monday: { available: true, minutes: 120 },
      tuesday: { available: true, minutes: 90 },
    },
    preferences: {
      frequency: { preferred_days: 6, min_days: 5, max_days: 7 },
      double_sessions: "sometimes",
      rest_days: "load_driven",
      facilities: ["pool", "gym", "mtb"],
      likes: "Teknisk terräng",
      dislikes: "",
    },
    constraints: { fixed_commitments: "Enduro måndag", other: "" },
    coach_autonomy: "week_auto",
  });
  assert.equal(result.ok, true);
  assert.equal(result.profile.preferences.frequency.preferred_days, 6);
  assert.equal(result.profile.goals.length, 2);
});

test("blank goal placeholder is accepted and removed from onboarding draft", () => {
  const result = validateAthleteProfile({
    schema_version: 1,
    status: "draft",
    current_step: 0,
    goals: [{ text: "", target_date: null, importance: "equal" }],
    availability: {},
    preferences: { frequency: {}, facilities: [] },
    constraints: { fixed_commitments: "", other: "" },
    coach_autonomy: "week_auto",
  });
  assert.equal(result.ok, true);
  assert.deepEqual(result.profile.goals, []);
});

test("blank goal placeholder is rejected for completed onboarding", () => {
  const result = validateAthleteProfile({
    schema_version: 1,
    status: "complete",
    current_step: 8,
    goals: [{ text: "", target_date: null, importance: "equal" }],
    availability: {},
    preferences: {
      frequency: { preferred_days: 6, min_days: 5, max_days: 7 },
      facilities: [],
    },
    constraints: { fixed_commitments: "", other: "" },
    coach_autonomy: "week_auto",
  });
  assert.equal(result.ok, false);
  assert.equal(result.reason, "invalid_goal_text");
});

test("athlete profile draft is persisted without triggering replanning", async () => {
  const calls = [];
  let body;
  const fakeFetch = async (url, init) => {
    calls.push(url);
    assert.equal(url, "https://example.supabase.co/rest/v1/rpc/training_upsert_athlete_profile");
    body = JSON.parse(init.body);
    return new Response(JSON.stringify({
      status: "saved",
      revision: 2,
      profile_status: "draft",
      planning_default: false,
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/profile", {
    method: "PUT",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
      "cf-access-authenticated-user-email": "athlete@example.com",
    },
    body: JSON.stringify({
      schema_version: 1,
      status: "draft",
      current_step: 2,
      goals: [{ text: "Bli allroundtränad.", target_date: null, importance: "equal" }],
      availability: {},
      preferences: { frequency: {}, facilities: [] },
      constraints: { fixed_commitments: "", other: "" },
      coach_autonomy: "week_auto",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  const responseBody = await response.json();
  assert.equal(responseBody.processing, "draft_saved");
  assert.equal(calls.length, 1);
  assert.match(body.p_athlete_subject, /^access:[0-9a-f]{32}$/);
  assert.equal(body.p_set_planning_default, false);
});

test("completed athlete profile persists as planning-ready without premature replan", async () => {
  const calls = [];
  let persistBody;
  const fakeFetch = async (url, init) => {
    calls.push(url);
    assert.equal(url, "https://example.supabase.co/rest/v1/rpc/training_upsert_athlete_profile");
    persistBody = JSON.parse(init.body);
    return new Response(JSON.stringify({
      status: "saved",
      revision: 3,
      profile_status: "complete",
      planning_default: true,
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/profile", {
    method: "PUT",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
      "cf-access-authenticated-user-email": "athlete@example.com",
    },
    body: JSON.stringify({
      schema_version: 1,
      status: "complete",
      current_step: 8,
      goals: [{ text: "Bli en stark allroundatlet.", target_date: null, importance: "equal" }],
      availability: { monday: { available: true, minutes: 90 } },
      preferences: {
        frequency: { preferred_days: 6, min_days: 5, max_days: 7 },
        double_sessions: "sometimes",
        rest_days: "load_driven",
        facilities: ["pool", "gym"],
        likes: "",
        dislikes: "",
      },
      constraints: { fixed_commitments: "", other: "" },
      coach_autonomy: "week_auto",
    }),
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).processing, "profile_saved");
  assert.equal(persistBody.p_set_planning_default, true);
  assert.equal(calls.length, 1);
});

test("athlete profile can be resumed from durable persistence", async () => {
  const fakeFetch = async (url, init) => {
    assert.equal(url, "https://example.supabase.co/rest/v1/rpc/training_get_athlete_profile");
    const body = JSON.parse(init.body);
    assert.match(body.p_athlete_subject, /^access:[0-9a-f]{32}$/);
    return new Response(JSON.stringify({
      status: "found",
      revision: 4,
      profile: {
        schema_version: 1,
        status: "draft",
        current_step: 3,
        goals: [{ text: "Testmål", target_date: null, importance: "equal" }],
      },
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request("https://xn--hll-qla.se/träning/training-api/profile", {
    method: "GET",
    headers: {
      "cf-access-jwt-assertion": "signed-access-jwt",
      "cf-access-authenticated-user-email": "athlete@example.com",
    },
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.status, "found");
  assert.equal(result.profile.current_step, 3);
});

test("completed athlete profile can start a durable canonical plan generation", async () => {
  let dispatchBody;
  const calls = [];
  const requestId = "9d0fca58-4c4d-4ef9-9158-c7b81fd11c51";
  const fakeFetch = async (url, init) => {
    calls.push(url);
    if (url.endsWith("/rest/v1/rpc/training_request_plan_generation")) {
      const body = JSON.parse(init.body);
      assert.match(body.p_athlete_subject, /^access:[0-9a-f]{32}$/);
      return new Response(JSON.stringify({
        status: "queued",
        request_id: requestId,
        profile_revision: 7,
        created: true,
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    assert.equal(url, "https://api.github.com/repos/perehall/hall.se/dispatches");
    dispatchBody = JSON.parse(init.body);
    return new Response(null, { status: 204 });
  };

  const request = new Request("https://xn--hll-qla.se/träning/training-api/profile/generate", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cf-access-jwt-assertion": "signed-access-jwt",
      "cf-access-authenticated-user-email": "athlete@example.com",
    },
    body: "{}",
  });
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.status, "queued");
  assert.equal(body.request_id, requestId);
  assert.equal(dispatchBody.event_type, "athlete-profile-plan-request");
  assert.equal(dispatchBody.client_payload.request_id, requestId);
  assert.equal(dispatchBody.client_payload.profile_revision, 7);
  assert.equal(calls.length, 2);
});

test("athlete can poll only their durable plan generation status", async () => {
  const requestId = "9d0fca58-4c4d-4ef9-9158-c7b81fd11c51";
  const fakeFetch = async (url, init) => {
    assert.equal(url, "https://example.supabase.co/rest/v1/rpc/training_get_plan_generation");
    const body = JSON.parse(init.body);
    assert.equal(body.p_request_id, requestId);
    assert.match(body.p_athlete_subject, /^access:[0-9a-f]{32}$/);
    return new Response(JSON.stringify({
      status: "running",
      request_id: requestId,
      profile_revision: 7,
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request(
    "https://xn--hll-qla.se/träning/training-api/profile/generate?id=" + requestId,
    {
      method: "GET",
      headers: {
        "cf-access-jwt-assertion": "signed-access-jwt",
        "cf-access-authenticated-user-email": "athlete@example.com",
      },
    },
  );
  const response = await handleRequest(request, env, fakeFetch);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).status, "running");
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


test("Wrangler keeps one canonical production config with required runtime secrets", () => {
  const config = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  assert.match(config, /"workers_dev"\s*:\s*true/);
  assert.match(config, /"name"\s*:\s*"hall-se"/);
  assert.match(config, /"SUPABASE_PROJECT_URL"\s*:\s*"https:\/\/izzevnhgtsvffpkccoai\.supabase\.co"/);

  for (const secret of [
    "WEBHOOK_PATH_SECRET",
    "STRAVA_VERIFY_TOKEN",
    "STRAVA_OWNER_ID",
    "STRAVA_SUBSCRIPTION_ID",
    "GITHUB_DISPATCH_TOKEN",
    "SUPABASE_SECRET_KEY",
  ]) {
    assert.ok(config.includes(`"${secret}"`), `missing required secret declaration: ${secret}`);
  }
});
