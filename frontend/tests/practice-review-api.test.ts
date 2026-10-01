import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

import {
  answerPracticeQuestion,
  generatePracticeQuestions,
  getPracticeQueue,
  getPracticeSummary,
} from "../lib/practice-review-api";

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

test("practice summary reads mastery and due counts", async () => {
  globalThis.fetch = async (input) => {
    assert.match(String(input), /\/api\/practice\/summary/);
    return jsonResponse({
      question_count: 3,
      due_count: 2,
      next_due_at: 10,
      attempt_count: 1,
      progress: [],
    });
  };

  const summary = await getPracticeSummary();
  assert.equal(summary.question_count, 3);
  assert.equal(summary.due_count, 2);
});

test("practice generation and queue use the selected knowledge base", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push(`${init?.method ?? "GET"} ${String(input)}`);
    return jsonResponse({ questions: [] });
  };

  await generatePracticeQuestions("资料库", 5);
  await getPracticeQueue("资料库");

  assert.match(calls[0], /POST .*\/api\/practice\/generate/);
  assert.match(calls[1], /knowledge_base=/);
  assert.match(calls[1], /%E8%B5%84%E6%96%99%E5%BA%93/);
});

test("practice answer sends the learner response and rating", async () => {
  let body: Record<string, unknown> | null = null;
  globalThis.fetch = async (input, init) => {
    assert.match(String(input), /\/api\/practice\/questions\/9\/answer/);
    body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    return jsonResponse({
      question_id: 9,
      rating: "good",
      interval_days: 4,
      due_at: 20,
      mastery_score: 8,
    });
  };

  const result = await answerPracticeQuestion(9, "我的解释", "good");
  assert.deepEqual(body, { answer: "我的解释", rating: "good" });
  assert.equal(result.interval_days, 4);
  assert.equal(result.mastery_score, 8);
});
