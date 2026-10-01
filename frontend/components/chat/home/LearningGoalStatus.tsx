"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Check, Target } from "lucide-react";
import { useTranslation } from "react-i18next";

import { fetchAuthStatus } from "@/lib/auth";
import {
  getPersonalizationStatus,
  setOwnLearnerProfile,
  type PersonalizationStatus,
} from "@/lib/profile-api";

export default function LearningGoalStatus() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<PersonalizationStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const auth = await fetchAuthStatus();
      if (cancelled || !auth?.enabled || !auth.authenticated) return;
      try {
        const next = await getPersonalizationStatus();
        if (!cancelled) setStatus(next);
      } catch {
        if (!cancelled) setStatus(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const complete = useCallback(async () => {
    if (!status?.learner_profile?.learning_goal) return;
    setBusy(true);
    try {
      const profile = await setOwnLearnerProfile({
        ...status.learner_profile,
        learning_goal_progress: 100,
        learning_goal_status: "completed",
      });
      setStatus({
        ...status,
        learner_profile: profile ?? {
          ...status.learner_profile,
          learning_goal_progress: 100,
          learning_goal_status: "completed",
        },
      });
    } finally {
      setBusy(false);
    }
  }, [status]);

  if (!status?.available || !status.learner_profile?.learning_goal) return null;
  const profile = status.learner_profile;
  const completed = profile.learning_goal_status === "completed";
  const progress = Math.max(
    0,
    Math.min(100, profile.learning_goal_progress ?? (completed ? 100 : 0)),
  );

  return (
    <div className="mx-auto flex w-full max-w-[960px] justify-end px-6 pb-1">
      <div className="w-full max-w-[620px] rounded-xl border border-[var(--border)] bg-[var(--card)]/70 px-3 py-2 text-[11.5px] text-[var(--muted-foreground)] shadow-sm backdrop-blur">
        <div className="flex items-center gap-2">
          <Target
            size={13}
            className={completed ? "text-emerald-500" : "text-[var(--primary)]"}
          />
          <span className="shrink-0 font-medium text-[var(--foreground)]">
            {completed ? t("Goal completed") : t("Current goal")}:
          </span>
          <span className="min-w-0 flex-1 truncate">
            {profile.learning_goal}
          </span>
          {!completed ? (
            <span className="shrink-0 font-medium text-[var(--foreground)]">
              {progress}%
            </span>
          ) : null}
          <Link
            href="/profile"
            className="shrink-0 font-medium text-[var(--primary)] hover:underline"
          >
            {t("Adjust")}
          </Link>
          {!completed ? (
            <button
              type="button"
              onClick={() => void complete()}
              disabled={busy}
              className="inline-flex shrink-0 items-center gap-1 font-medium text-emerald-600 hover:underline disabled:opacity-50 dark:text-emerald-400"
            >
              <Check size={12} />
              {t("Complete")}
            </button>
          ) : null}
        </div>
        {!completed ? (
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--muted)]">
            <div
              className="h-full rounded-full bg-[var(--primary)]"
              style={{ width: `${progress}%` }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
