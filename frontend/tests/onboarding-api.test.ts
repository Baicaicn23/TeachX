import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  completeOnboarding,
  getOnboardingStatus,
  saveOnboardingMaterials,
} from "../lib/onboarding-api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("getOnboardingStatus reads the persisted completion state", async () => {
  globalThis.fetch = async (input) => {
    assert.match(String(input), /\/api\/auth\/onboarding/);
    return jsonResponse({
      available: true,
      completed: false,
      learner_profile: null,
    });
  };

  assert.deepEqual(await getOnboardingStatus(), {
    available: true,
    completed: false,
    learner_profile: null,
  });
});

test("completeOnboarding calls the dedicated completion endpoint", async () => {
  let request: RequestInit | undefined;
  globalThis.fetch = async (input, init) => {
    assert.match(String(input), /\/api\/auth\/onboarding\/complete/);
    request = init;
    return jsonResponse({ completed: true });
  };

  await completeOnboarding();
  assert.equal(request?.method, "POST");
});

test("saveOnboardingMaterials creates a user-scoped knowledge base", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(String(input));
    if (calls.length === 1) return jsonResponse({ knowledge_bases: [] });
    const form = init?.body as FormData;
    assert.equal(form.get("name"), "学习资料-abc123");
    assert.equal(form.get("rag_provider"), "sqlite-fts");
    return jsonResponse({ task_id: "task-1" });
  };

  await saveOnboardingMaterials(
    [new File(["hello"], "notes.txt", { type: "text/plain" })],
    "abc123",
  );

  assert.equal(calls.length, 2);
  assert.match(calls[1], /\/api\/knowledge-bases/);
});

test("saveOnboardingMaterials retries into an existing knowledge base", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input) => {
    calls.push(String(input));
    if (calls.length === 1) {
      return jsonResponse({ knowledge_bases: [{ name: "学习资料-abc123" }] });
    }
    return jsonResponse({ task_id: "task-2" });
  };

  await saveOnboardingMaterials(
    [new File(["hello"], "notes.txt", { type: "text/plain" })],
    "abc123",
  );

  assert.equal(calls.length, 2);
  assert.match(calls[1], /\/api\/knowledge-bases\/%E5%AD%A6%E4%B9%A0%E8%B5%84%E6%96%99-abc123\/upload/);
});
