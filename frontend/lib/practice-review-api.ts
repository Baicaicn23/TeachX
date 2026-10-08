import { apiFetch, apiUrl } from "@/lib/api";

export type PracticeRating = "again" | "hard" | "good" | "easy";

/** 出题来源:从知识库片段,或从学生自己记过的误区(错题)。 */
export type PracticeSource = "knowledge_base" | "mistakes";

export interface PracticeKnowledgeBase {
  name: string;
  document_count: number;
  chunk_count: number;
}

export interface PracticeProgress {
  knowledge_base: string;
  mastery_score: number;
  attempt_count: number;
  updated_at: number;
}

export interface PracticeSummary {
  question_count: number;
  due_count: number;
  next_due_at: number | null;
  attempt_count: number;
  progress: PracticeProgress[];
}

export interface PracticeQuestion {
  id: number;
  knowledge_base: string;
  prompt: string;
  source_excerpt: string;
  /** "mistake" 表示这道题出自学生记过的误区。 */
  source?: PracticeSource | "mistake";
  /** 只在刚出题时的响应里出现:"model" 表示由模型写题,"template" 表示模板出题。 */
  generator?: "model" | "template";
  source_document?: string;
  created_at: number;
  mastery_score: number;
  rating: PracticeRating | null;
  answer: string;
  due_at: number | null;
  attempt_count: number;
}

export interface PracticeAnswerResult {
  question_id: number;
  rating: PracticeRating;
  interval_days: number;
  due_at: number;
  mastery_score: number;
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // Fall back to the stable message below.
  }
  return fallback;
}

export async function getPracticeSummary(): Promise<PracticeSummary> {
  const response = await apiFetch(apiUrl("/api/practice/summary"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load practice summary"));
  }
  return (await response.json()) as PracticeSummary;
}

export async function getPracticeKnowledgeBases(): Promise<
  PracticeKnowledgeBase[]
> {
  const response = await apiFetch(apiUrl("/api/practice/knowledge-bases"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load knowledge bases"));
  }
  const body = (await response.json()) as {
    knowledge_bases?: PracticeKnowledgeBase[];
  };
  return Array.isArray(body.knowledge_bases) ? body.knowledge_bases : [];
}

export async function getPracticeQueue(
  knowledgeBase = "",
  limit = 10,
): Promise<PracticeQuestion[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (knowledgeBase) params.set("knowledge_base", knowledgeBase);
  const response = await apiFetch(
    apiUrl(`/api/practice/queue?${params.toString()}`),
    { cache: "no-store" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load practice queue"));
  }
  const body = (await response.json()) as { questions?: PracticeQuestion[] };
  return Array.isArray(body.questions) ? body.questions : [];
}

export async function generatePracticeQuestions(
  knowledgeBase: string,
  count: number,
  source: PracticeSource = "knowledge_base",
): Promise<PracticeQuestion[]> {
  const response = await apiFetch(apiUrl("/api/practice/generate"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ knowledge_base: knowledgeBase, count, source }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to generate practice"));
  }
  const body = (await response.json()) as { questions?: PracticeQuestion[] };
  return Array.isArray(body.questions) ? body.questions : [];
}

export async function answerPracticeQuestion(
  questionId: number,
  answer: string,
  rating: PracticeRating,
): Promise<PracticeAnswerResult> {
  const response = await apiFetch(
    apiUrl(`/api/practice/questions/${questionId}/answer`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, rating }),
    },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to save practice answer"));
  }
  return (await response.json()) as PracticeAnswerResult;
}
