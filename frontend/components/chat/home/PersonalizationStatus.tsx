"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { fetchAuthStatus } from "@/lib/auth";
import {
  getPersonalizationStatus,
  setPersonalizationEnabled,
  type PersonalizationStatus as PersonalizationStatusData,
} from "@/lib/profile-api";

export default function PersonalizationStatus() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<PersonalizationStatusData | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const auth = await fetchAuthStatus();
    if (!auth?.enabled || !auth.authenticated) return;
    try {
      setStatus(await getPersonalizationStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = useCallback(async () => {
    if (!status) return;
    setBusy(true);
    try {
      const enabled = await setPersonalizationEnabled(!status.enabled);
      setStatus({ ...status, enabled });
    } finally {
      setBusy(false);
    }
  }, [status]);

  if (!status) return null;

  const profile = status.learner_profile ?? {};
  const summary = [profile.grade_level, profile.explanation_style]
    .filter(Boolean)
    .join(" · ");
  const hasProfile = status.available;
  const label = status.enabled
    ? hasProfile
      ? `${t("Personalization")}: ${summary}`
      : t("Complete learner profile")
    : t("Personalization is off");

  return (
    <div className="mx-auto flex w-full max-w-[960px] justify-end px-6 pb-1">
      <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--card)]/70 px-2.5 py-1 text-[11.5px] text-[var(--muted-foreground)] shadow-sm backdrop-blur">
        <Sparkles
          size={13}
          strokeWidth={1.8}
          className={status.enabled ? "text-[var(--primary)]" : ""}
        />
        <span className="truncate">{label}</span>
        <Link
          href="/profile"
          className="shrink-0 font-medium text-[var(--primary)] hover:underline"
        >
          {hasProfile ? t("Edit") : t("Set up")}
        </Link>
        {hasProfile ? (
          <button
            type="button"
            onClick={() => void toggle()}
            disabled={busy}
            className="shrink-0 hover:text-[var(--foreground)] disabled:opacity-50"
          >
            {status.enabled ? t("Turn off") : t("Turn on")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
