import { apiFetch, apiUrl } from "@/lib/api";

export type AnswerFeedbackRating = "helpful" | "unclear" | "wrong";

export interface AnswerFeedbackRecord {
  id: number;
  session_id: string;
  message_id: number;
  rating: AnswerFeedbackRating;
  note: string;
  session_title: string;
  question: string;
  answer: string;
  capability: string;
  created_at: number;
  updated_at: number;
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // Fall through to the stable caller-facing message.
  }
  return fallback;
}

export async function listSessionAnswerFeedback(
  sessionId: string,
): Promise<AnswerFeedbackRecord[]> {
  const params = new URLSearchParams({ session_id: sessionId });
  const response = await apiFetch(
    apiUrl(`/api/learning/feedback?${params.toString()}`),
    { cache: "no-store" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load answer feedback"));
  }
  const body = (await response.json()) as { records?: AnswerFeedbackRecord[] };
  return Array.isArray(body.records) ? body.records : [];
}

export async function upsertAnswerFeedback(
  messageId: number,
  rating: AnswerFeedbackRating,
  note = "",
): Promise<AnswerFeedbackRecord> {
  const response = await apiFetch(
    apiUrl(`/api/learning/feedback/${encodeURIComponent(String(messageId))}`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, note }),
    },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to save answer feedback"));
  }
  const body = (await response.json()) as { record: AnswerFeedbackRecord };
  return body.record;
}

export async function listAnswerFeedbackRecords(
  rating?: AnswerFeedbackRating,
): Promise<AnswerFeedbackRecord[]> {
  const params = new URLSearchParams();
  if (rating) params.set("rating", rating);
  const query = params.size ? `?${params.toString()}` : "";
  const response = await apiFetch(apiUrl(`/api/learning/records${query}`), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load learning records"));
  }
  const body = (await response.json()) as { records?: AnswerFeedbackRecord[] };
  return Array.isArray(body.records) ? body.records : [];
}

export async function deleteAnswerFeedbackRecord(recordId: number): Promise<void> {
  const response = await apiFetch(
    apiUrl(`/api/learning/records/${encodeURIComponent(String(recordId))}`),
    { method: "DELETE" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to delete learning record"));
  }
}
