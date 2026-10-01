import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  deleteAnswerFeedbackRecord,
  listAnswerFeedbackRecords,
  listSessionAnswerFeedback,
  upsertAnswerFeedback,
} from "../lib/answer-feedback-api";

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

test("session feedback is scoped to one conversation", async () => {
  globalThis.fetch = async (input) => {
    const url = String(input);
    assert.match(url, /\/api\/learning\/feedback\?/);
    assert.match(url, /session_id=session-1/);
    return jsonResponse({ records: [] });
  };

  assert.deepEqual(await listSessionAnswerFeedback("session-1"), []);
});

test("answer feedback upsert sends the selected rating and note", async () => {
  let body: Record<string, unknown> | null = null;
  globalThis.fetch = async (input, init) => {
    assert.match(String(input), /\/api\/learning\/feedback\/42/);
    assert.equal(init?.method, "PUT");
    body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    return jsonResponse({
      record: {
        id: 7,
        session_id: "session-1",
        message_id: 42,
        rating: "wrong",
        note: "混淆了条件和结论",
        session_title: "线性代数",
        question: "为什么？",
        answer: "因为……",
        capability: "chat",
        created_at: 1,
        updated_at: 2,
      },
    });
  };

  const record = await upsertAnswerFeedback(42, "wrong", "混淆了条件和结论");
  assert.deepEqual(body, { rating: "wrong", note: "混淆了条件和结论" });
  assert.equal(record.id, 7);
});

test("learning record list and delete use the owner-scoped API", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (init?.method === "DELETE") return jsonResponse({ deleted: true });
    return jsonResponse({ records: [] });
  };

  await listAnswerFeedbackRecords("wrong");
  await deleteAnswerFeedbackRecord(7);

  assert.match(calls[0], /GET .*\/api\/learning\/records\?rating=wrong/);
  assert.match(calls[1], /DELETE .*\/api\/learning\/records\/7/);
});
