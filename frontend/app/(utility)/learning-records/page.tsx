"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  HelpCircle,
  MessageSquare,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  deleteAnswerFeedbackRecord,
  listAnswerFeedbackRecords,
  type AnswerFeedbackRating,
  type AnswerFeedbackRecord,
} from "@/lib/answer-feedback-api";
import { formatDate, type Language } from "@/lib/datetime";
import { notify } from "@/lib/notifications";
import { saveWorkspaceDraft } from "@/lib/workspace-drafts";

type Filter = "all" | AnswerFeedbackRating;

const FILTERS: Array<{ value: Filter; label: string; icon: typeof BookOpenCheck }> = [
  { value: "all", label: "All records", icon: BookOpenCheck },
  { value: "helpful", label: "Helpful", icon: CheckCircle2 },
  { value: "unclear", label: "Unclear", icon: HelpCircle },
  { value: "wrong", label: "My misunderstandings", icon: AlertTriangle },
];

function ratingLabel(rating: AnswerFeedbackRating, t: (key: string) => string) {
  if (rating === "helpful") return t("Helpful");
  if (rating === "unclear") return t("Unclear");
  return t("My misunderstanding");
}

function truncate(value: string, limit = 320): string {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > limit ? `${clean.slice(0, limit)}…` : clean;
}

export default function LearningRecordsPage() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const [records, setRecords] = useState<AnswerFeedbackRecord[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void listAnswerFeedbackRecords()
      .then((next) => {
        if (!cancelled) setRecords(next);
      })
      .catch(() => {
        if (!cancelled) setError(t("Could not load learning records"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const visible = useMemo(
    () => (filter === "all" ? records : records.filter((record) => record.rating === filter)),
    [filter, records],
  );

  async function remove(record: AnswerFeedbackRecord) {
    if (!window.confirm(t("Delete this learning record? This cannot be undone."))) {
      return;
    }
    setBusyId(record.id);
    try {
      await deleteAnswerFeedbackRecord(record.id);
      setRecords((current) => current.filter((item) => item.id !== record.id));
      notify(t("Learning record deleted"), { tone: "success" });
    } catch {
      notify(t("Could not delete learning record"), { tone: "error" });
    } finally {
      setBusyId(null);
    }
  }

  async function reviewMisunderstanding(record: AnswerFeedbackRecord) {
    const note = record.note.trim().replace(/[。.!?！？]+$/, "");
    await saveWorkspaceDraft(
      {
        text: t(
          "I wrote this misunderstanding in my learning records: {{note}}. Please ask one diagnostic question, then explain it again in a different way.",
          { note },
        ),
        attachments: [],
      },
      undefined,
      "/chat",
    );
    router.push("/chat");
  }

  const counts = useMemo(
    () => ({
      helpful: records.filter((record) => record.rating === "helpful").length,
      unclear: records.filter((record) => record.rating === "unclear").length,
      wrong: records.filter((record) => record.rating === "wrong").length,
    }),
    [records],
  );

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-7 sm:px-6">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-emerald-500/10 p-2.5 text-emerald-600 dark:text-emerald-400">
          <BookOpenCheck size={22} />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--foreground)]">
            {t("Learning records")}
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
            {t(
              "Review the answers that helped, the explanations that were unclear, and the misunderstandings you wrote down.",
            )}
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTERS.map((item) => {
          const Icon = item.icon;
          const active = filter === item.value;
          const count =
            item.value === "all"
              ? records.length
              : counts[item.value as AnswerFeedbackRating];
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => setFilter(item.value)}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? "border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]"
                  : "border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              <Icon size={14} />
              {t(item.label)}
              <span className="rounded-full bg-[var(--muted)] px-1.5 py-0.5 text-[10px]">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8 text-center text-sm text-[var(--muted-foreground)]">
          {t("Loading learning records…")}
        </div>
      ) : error ? (
        <div className="mt-6 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      ) : visible.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--border)] bg-[var(--card)] px-6 py-12 text-center">
          <MessageSquare
            size={28}
            className="mx-auto text-[var(--muted-foreground)]/50"
          />
          <h2 className="mt-3 text-sm font-medium text-[var(--foreground)]">
            {t("No learning records here yet")}
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm leading-6 text-[var(--muted-foreground)]">
            {t(
              "Use the feedback controls under a tutor answer to mark it helpful, unclear, or record a misunderstanding.",
            )}
          </p>
          <button
            type="button"
            onClick={() => router.push("/chat")}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3.5 py-2 text-sm font-medium text-[var(--primary-foreground)] hover:opacity-90"
          >
            {t("Go to chat")}
            <ArrowRight size={15} />
          </button>
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {visible.map((record) => (
            <article
              key={record.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                      record.rating === "helpful"
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                        : record.rating === "unclear"
                          ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                          : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                    }`}
                  >
                    {record.rating === "helpful" ? (
                      <CheckCircle2 size={13} />
                    ) : record.rating === "unclear" ? (
                      <HelpCircle size={13} />
                    ) : (
                      <AlertTriangle size={13} />
                    )}
                    {ratingLabel(record.rating, t)}
                  </span>
                  <span className="truncate text-xs text-[var(--muted-foreground)]">
                    {record.session_title || t("Untitled conversation")}
                  </span>
                </div>
                <span className="text-xs text-[var(--muted-foreground)]">
                  {formatDate(
                    new Date(record.updated_at * 1000),
                    i18n.language as Language,
                  )}
                </span>
              </div>

              {record.question ? (
                <div className="mt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
                    {t("Question")}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[var(--foreground)]">
                    {truncate(record.question)}
                  </p>
                </div>
              ) : null}

              <div className="mt-3 rounded-xl bg-[var(--muted)]/35 px-3.5 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
                  {t("Tutor answer")}
                </p>
                <p className="mt-1 text-sm leading-6 text-[var(--foreground)]">
                  {truncate(record.answer)}
                </p>
              </div>

              {record.rating === "wrong" && record.note ? (
                <div className="mt-3 rounded-xl border border-amber-500/25 bg-amber-500/5 px-3.5 py-3">
                  <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
                    {t("My misunderstanding")}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[var(--foreground)]">
                    {record.note}
                  </p>
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => router.push(`/chat/${record.session_id}`)}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  <MessageSquare size={14} />
                  {t("Open original conversation")}
                </button>
                <div className="flex items-center gap-2">
                  {record.rating === "wrong" && record.note ? (
                    <button
                      type="button"
                      onClick={() => router.push("/practice?source=mistakes")}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] hover:opacity-80"
                    >
                      <BookOpenCheck size={14} />
                      {t("Practice this mistake")}
                    </button>
                  ) : null}
                  {record.rating === "wrong" && record.note ? (
                    <button
                      type="button"
                      onClick={() => void reviewMisunderstanding(record)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-xs font-medium text-[var(--primary-foreground)] hover:opacity-90"
                    >
                      <ArrowRight size={14} />
                      {t("Work through it again")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void remove(record)}
                    disabled={busyId === record.id}
                    aria-label={t("Delete learning record")}
                    className="rounded-lg p-1.5 text-[var(--muted-foreground)] hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
