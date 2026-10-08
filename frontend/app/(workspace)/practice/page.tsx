"use client";

import { useCallback, useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Brain,
  CalendarClock,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  Gauge,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatDate, type Language } from "@/lib/datetime";
import { notify } from "@/lib/notifications";
import {
  answerPracticeQuestion,
  generatePracticeQuestions,
  getPracticeKnowledgeBases,
  getPracticeQueue,
  getPracticeSummary,
  type PracticeKnowledgeBase,
  type PracticeQuestion,
  type PracticeRating,
  type PracticeSource,
  type PracticeSummary,
} from "@/lib/practice-review-api";

const RATINGS: Array<{
  value: PracticeRating;
  label: string;
  hint: string;
  interval: string;
  tone: string;
}> = [
  {
    value: "again",
    label: "Again",
    hint: "I could not explain it",
    interval: "Review tomorrow",
    tone: "border-red-500/30 text-red-600 dark:text-red-400",
  },
  {
    value: "hard",
    label: "Hard",
    hint: "I remembered only part of it",
    interval: "Review in 2 days",
    tone: "border-amber-500/30 text-amber-600 dark:text-amber-400",
  },
  {
    value: "good",
    label: "Good",
    hint: "I explained the main idea",
    interval: "Review in 4 days",
    tone: "border-blue-500/30 text-blue-600 dark:text-blue-400",
  },
  {
    value: "easy",
    label: "Easy",
    hint: "I can explain and apply it",
    interval: "Review in 7 days",
    tone: "border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
  },
];

export default function PracticePage() {
  const { t, i18n } = useTranslation();
  const answerId = useId();
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<PracticeKnowledgeBase[]>([]);
  const [queue, setQueue] = useState<PracticeQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState("");
  const [source, setSource] = useState<PracticeSource>("knowledge_base");
  const [questionCount, setQuestionCount] = useState(3);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");

  // 学习记录页的"用它出练习题"会带 ?source=mistakes 过来。用 location 直接读,
  // 不用 useSearchParams——后者在预渲染时需要 Suspense 边界。
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("source");
    if (requested === "mistakes") setSource("mistakes");
  }, []);

  const refresh = useCallback(async () => {
    const [nextSummary, nextBases, nextQueue] = await Promise.all([
      getPracticeSummary(),
      getPracticeKnowledgeBases(),
      getPracticeQueue(),
    ]);
    setSummary(nextSummary);
    setKnowledgeBases(nextBases);
    setQueue(nextQueue);
    setCurrentIndex(0);
    setSelectedKnowledgeBase((current) => current || nextBases[0]?.name || "");
  }, []);

  useEffect(() => {
    let cancelled = false;
    void refresh()
      .catch(() => {
        if (!cancelled) setError(t("Could not load practice"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refresh, t]);

  const averageMastery = useMemo(() => {
    if (!summary?.progress.length) return 0;
    return Math.round(
      summary.progress.reduce((total, row) => total + row.mastery_score, 0) /
        summary.progress.length,
    );
  }, [summary]);

  const currentQuestion = queue[currentIndex] ?? null;

  async function generate() {
    // "从错题出题"不需要选知识库——错题的学科已经记在题目上了。
    if (source === "knowledge_base" && !selectedKnowledgeBase) return;
    setGenerating(true);
    setError("");
    setSavedMessage("");
    try {
      const created = await generatePracticeQuestions(
        source === "knowledge_base" ? selectedKnowledgeBase : "",
        questionCount,
        source,
      );
      const [nextSummary, nextQueue] = await Promise.all([
        getPracticeSummary(),
        getPracticeQueue(),
      ]);
      setSummary(nextSummary);
      setQueue(nextQueue);
      setCurrentIndex(0);
      setAnswer("");
      notify(
        t("{{count}} practice questions generated", { count: created.length }),
        { tone: "success" },
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : t("Could not generate practice"),
      );
    } finally {
      setGenerating(false);
    }
  }

  async function submit(rating: PracticeRating) {
    if (!currentQuestion || !answer.trim()) return;
    setSaving(true);
    setError("");
    try {
      const result = await answerPracticeQuestion(
        currentQuestion.id,
        answer.trim(),
        rating,
      );
      setSavedMessage(
        t(
          "Answer saved. Review scheduled for {{date}}; mastery is now {{score}}%.",
          {
            date: formatDate(
              new Date(result.due_at * 1000),
              i18n.language as Language,
            ),
            score: result.mastery_score,
          },
        ),
      );
      setAnswer("");
      setCurrentIndex((current) => current + 1);
      setSummary(await getPracticeSummary());
      if (currentIndex + 1 >= queue.length) {
        setQueue(await getPracticeQueue());
        setCurrentIndex(0);
      }
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : t("Could not save practice answer"),
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 text-sm text-[var(--muted-foreground)] sm:px-6">
        {t("Loading practice…")}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-7 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-violet-500/10 p-2.5 text-violet-600 dark:text-violet-400">
            <Brain size={22} />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--foreground)]">
              {t("Practice and review")}
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
              {t(
                "Turn knowledge-base material into recall practice, then let your confidence schedule the next review.",
              )}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        >
          <RefreshCcw size={14} />
          {t("Refresh")}
        </button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <SummaryCard
          icon={CalendarClock}
          label={t("Due now")}
          value={summary?.due_count ?? 0}
        />
        <SummaryCard
          icon={Database}
          label={t("Practice questions")}
          value={summary?.question_count ?? 0}
        />
        <SummaryCard
          icon={Gauge}
          label={t("Average mastery")}
          value={`${averageMastery}%`}
        />
      </div>

      {summary?.progress.length ? (
        <section className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h2 className="text-sm font-semibold text-[var(--foreground)]">
            {t("Mastery by knowledge base")}
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {summary.progress.map((row) => (
              <div key={row.knowledge_base}>
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="truncate font-medium text-[var(--foreground)]">
                    {row.knowledge_base}
                  </span>
                  <span className="text-[var(--muted-foreground)]">
                    {row.mastery_score}% · {t("{{count}} reviews", { count: row.attempt_count })}
                  </span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--muted)]">
                  <div
                    className="h-full rounded-full bg-[var(--primary)] transition-all"
                    style={{ width: `${row.mastery_score}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {error ? (
        <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      ) : null}
      {savedMessage ? (
        <div className="mt-5 flex items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          {savedMessage}
        </div>
      ) : null}

      <section className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm sm:p-6">
        {currentQuestion ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <span className="rounded-full bg-[var(--muted)] px-2.5 py-1 font-medium text-[var(--foreground)]">
                  {currentQuestion.knowledge_base}
                </span>
                {currentQuestion.source === "mistake" ? (
                  <span className="rounded-full border border-[var(--primary)]/40 px-2.5 py-1 font-medium text-[var(--primary)]">
                    {t("From your mistake")}
                  </span>
                ) : null}
                <span>
                  {t("Question {{current}} of {{total}}", {
                    current: currentIndex + 1,
                    total: queue.length,
                  })}
                </span>
              </div>
              <span className="text-xs text-[var(--muted-foreground)]">
                {t("Mastery {{score}}%", {
                  score: currentQuestion.mastery_score,
                })}
              </span>
            </div>
            <h2 className="mt-5 whitespace-pre-wrap text-base font-medium leading-7 text-[var(--foreground)]">
              {currentQuestion.prompt}
            </h2>
            <label
              htmlFor={answerId}
              className="mt-5 block text-sm font-medium text-[var(--foreground)]"
            >
              {t("Your answer")}
            </label>
            <textarea
              id={answerId}
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              rows={6}
              placeholder={t("Explain it in your own words…")}
              className="mt-2 w-full resize-y rounded-xl border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm leading-6 text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] focus:ring-2 focus:ring-[var(--primary)]"
            />
            <div className="mt-5">
              <p className="mb-2 text-xs font-medium text-[var(--muted-foreground)]">
                {t("How well could you explain it?")}
              </p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {RATINGS.map((rating) => (
                  <button
                    key={rating.value}
                    type="button"
                    disabled={saving || !answer.trim()}
                    onClick={() => void submit(rating.value)}
                    className={`rounded-xl border bg-[var(--background)] px-3 py-3 text-left transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40 ${rating.tone}`}
                  >
                    <span className="block text-sm font-semibold">
                      {t(rating.label)}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--muted-foreground)]">
                      {t(rating.hint)}
                    </span>
                    <span className="mt-2 block text-[11px]">{t(rating.interval)}</span>
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="py-4 text-center">
            <CircleHelp
              size={30}
              className="mx-auto text-[var(--muted-foreground)]/55"
            />
            <h2 className="mt-3 text-base font-semibold text-[var(--foreground)]">
              {summary?.question_count
                ? t("No practice is due")
                : t("Create your first practice questions")}
            </h2>
            <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-[var(--muted-foreground)]">
              {summary?.question_count
                ? t("Come back when a review is due, or generate more questions from another knowledge base.")
                : t("Choose a knowledge base and TeachX will turn its material into recall questions.")}
            </p>
            {summary?.next_due_at ? (
              <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
                <Clock3 size={14} />
                {t("Next review: {{date}}", {
                  date: formatDate(
                    new Date(summary.next_due_at * 1000),
                    i18n.language as Language,
                  ),
                })}
              </p>
            ) : null}
          </div>
        )}
      </section>

      <section className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <div className="flex items-start gap-2">
          <Sparkles size={17} className="mt-0.5 text-violet-500" />
          <div>
            <h2 className="text-sm font-semibold text-[var(--foreground)]">
              {t("Generate more practice")}
            </h2>
            <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
              {source === "knowledge_base"
                ? t(
                    "Each unused text chunk becomes one open-ended recall question.",
                  )
                : t(
                    "Each saved misunderstanding becomes a new question on the same idea.",
                  )}
            </p>
          </div>
        </div>
        {knowledgeBases.length ? (
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="text-xs text-[var(--muted-foreground)]">
              {t("Question source")}
              <select
                value={source}
                onChange={(event) =>
                  setSource(event.target.value as PracticeSource)
                }
                className="mt-1.5 block rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
              >
                <option value="knowledge_base">
                  {t("From knowledge base")}
                </option>
                <option value="mistakes">{t("From my mistakes")}</option>
              </select>
            </label>
            {source === "knowledge_base" ? (
              <label className="min-w-[220px] flex-1 text-xs text-[var(--muted-foreground)]">
                {t("Knowledge base")}
                <select
                  value={selectedKnowledgeBase}
                  onChange={(event) =>
                    setSelectedKnowledgeBase(event.target.value)
                  }
                  className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
                >
                  {knowledgeBases.map((base) => (
                    <option key={base.name} value={base.name}>
                      {base.name} · {base.chunk_count} {t("chunks")}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="text-xs text-[var(--muted-foreground)]">
              {t("Question count")}
              <select
                value={questionCount}
                onChange={(event) => setQuestionCount(Number(event.target.value))}
                className="mt-1.5 block rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
              >
                {[1, 3, 5, 10].map((count) => (
                  <option key={count} value={count}>
                    {count}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void generate()}
              disabled={
                generating ||
                (source === "knowledge_base" && !selectedKnowledgeBase)
              }
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
            >
              {generating ? t("Generating…") : t("Generate questions")}
              {!generating && <ArrowRight size={15} />}
            </button>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-[var(--border)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
            {t(
              "Upload a TXT, Markdown, or PDF to a knowledge base before creating practice.",
            )}{" "}
            <Link href="/knowledge-bases" className="text-[var(--primary)] hover:underline">
              {t("Open knowledge bases")}
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof CalendarClock;
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <Icon size={15} />
        {label}
      </div>
      <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{value}</p>
    </div>
  );
}
