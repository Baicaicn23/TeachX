"use client";

import { useEffect, useId, useState } from "react";
import { AlertTriangle, Check, HelpCircle, ThumbsUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import type {
  AnswerFeedbackRating,
  AnswerFeedbackRecord,
} from "@/lib/answer-feedback-api";
import Tooltip from "@/shared/ui/Tooltip";

function FeedbackButton({
  label,
  active,
  disabled,
  icon: Icon,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  icon: typeof ThumbsUp;
  onClick: () => void;
}) {
  return (
    <Tooltip label={label} side="top">
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        disabled={disabled}
        onClick={onClick}
        className={`inline-flex items-center justify-center rounded-md p-1 transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
          active
            ? "bg-[var(--primary)]/10 text-[var(--primary)]"
            : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50 hover:text-[var(--foreground)]"
        }`}
      >
        <Icon size={15} strokeWidth={active ? 2 : 1.5} />
      </button>
    </Tooltip>
  );
}

export function AnswerFeedbackActions({
  record,
  busy,
  onSave,
  onDelete,
}: {
  record?: AnswerFeedbackRecord;
  busy: boolean;
  onSave: (rating: AnswerFeedbackRating, note?: string) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const editorId = useId();
  const [editingMistake, setEditingMistake] = useState(false);
  const [note, setNote] = useState(record?.note ?? "");

  useEffect(() => {
    setNote(record?.note ?? "");
  }, [record?.id, record?.note]);

  async function select(rating: AnswerFeedbackRating) {
    if (rating === "wrong") {
      setEditingMistake(true);
      return;
    }
    if (record?.rating === rating) {
      await onDelete();
      return;
    }
    await onSave(rating, "");
  }

  return (
    <div className="mt-1.5">
      <div className="flex items-center gap-1">
        <FeedbackButton
          label={t("Helpful")}
          icon={ThumbsUp}
          active={record?.rating === "helpful"}
          disabled={busy}
          onClick={() => void select("helpful")}
        />
        <FeedbackButton
          label={t("Unclear")}
          icon={HelpCircle}
          active={record?.rating === "unclear"}
          disabled={busy}
          onClick={() => void select("unclear")}
        />
        <FeedbackButton
          label={t("Record my misunderstanding")}
          icon={AlertTriangle}
          active={record?.rating === "wrong"}
          disabled={busy}
          onClick={() => void select("wrong")}
        />
      </div>

      {record?.rating === "wrong" && record.note && !editingMistake ? (
        <div className="mt-1 flex max-w-[min(560px,90vw)] items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-2 text-xs text-[var(--foreground)]">
          <span className="min-w-0 flex-1 leading-5">
            <span className="font-medium">{t("My misunderstanding")}: </span>
            {record.note}
          </span>
          <button
            type="button"
            onClick={() => setEditingMistake(true)}
            className="shrink-0 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            {t("Edit")}
          </button>
          <button
            type="button"
            onClick={() => void onDelete()}
            disabled={busy}
            className="shrink-0 text-red-500/80 hover:text-red-600 disabled:opacity-50"
          >
            {t("Delete")}
          </button>
        </div>
      ) : null}

      {editingMistake ? (
        <div className="mt-2 max-w-[min(560px,90vw)] rounded-xl border border-[var(--border)] bg-[var(--background)] p-3 shadow-sm">
          <label
            htmlFor={editorId}
            className="text-xs font-medium text-[var(--foreground)]"
          >
            {t("Where did your understanding go wrong?")}
          </label>
          <textarea
            id={editorId}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={t("Example: I confused the condition with the conclusion.")}
            className="mt-2 w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] focus:ring-2 focus:ring-[var(--primary)]"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEditingMistake(false);
                setNote(record?.note ?? "");
              }}
              disabled={busy}
              className="rounded-lg px-3 py-1.5 text-xs text-[var(--muted-foreground)] hover:bg-[var(--muted)] disabled:opacity-50"
            >
              {t("Cancel")}
            </button>
            <button
              type="button"
              disabled={busy || !note.trim()}
              onClick={() =>
                void onSave("wrong", note.trim()).then(() => setEditingMistake(false))
              }
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-xs font-medium text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
            >
              <Check size={14} />
              {t("Save")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
