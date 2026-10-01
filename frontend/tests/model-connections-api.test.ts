import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  activateModelConnection,
  listModelConnections,
  saveModelConnection,
  testModelConnection,
} from "../lib/model-connections-api";

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

test("model connections list separates platform default from user connections", async () => {
  globalThis.fetch = async (input) => {
    assert.match(String(input), /\/api\/model-connections/);
    return jsonResponse({
      platform_default: {
        provider: "openai",
        model: "deepseek-flash",
        base_url: "https://api.deepseek.com/v1",
      },
      connections: [],
    });
  };

  const data = await listModelConnections();
  assert.equal(data.platform_default.model, "deepseek-flash");
});

test("model connection save and test send the provider configuration", async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({
      url: String(input),
      body: JSON.parse(String(init?.body)) as Record<string, unknown>,
    });
    if (String(input).includes("/api/model-connections/test")) {
      return jsonResponse({ models: ["deepseek-flash"] });
    }
    return jsonResponse({
      connection: {
        id: "connection-1",
        name: "DeepSeek Flash",
        base_url: "https://api.deepseek.com/v1",
        default_model: "deepseek-flash",
        models: ["deepseek-flash"],
        active: true,
        has_api_key: true,
        created_at: 1,
        updated_at: 1,
      },
    });
  };

  const models = await testModelConnection({
    base_url: "https://api.deepseek.com/v1",
    api_key: "secret",
  });
  const saved = await saveModelConnection({
    name: "DeepSeek Flash",
    base_url: "https://api.deepseek.com/v1",
    api_key: "secret",
    default_model: "deepseek-flash",
    models,
  });

  assert.equal(calls[0].url.includes("/api/model-connections/test"), true);
  assert.equal(calls[1].body.default_model, "deepseek-flash");
  assert.equal(saved.active, true);
});

test("activating a connection targets its owner-scoped route", async () => {
  globalThis.fetch = async (input) => {
    assert.match(String(input), /\/api\/model-connections\/connection-1\/activate/);
    return jsonResponse({ ok: true });
  };

  await activateModelConnection("connection-1");
});
