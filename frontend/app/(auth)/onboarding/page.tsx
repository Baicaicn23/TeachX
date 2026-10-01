"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  FileText,
  MessageSquareText,
  Target,
  Upload,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { fetchAuthStatus } from "@/lib/auth";
import {
  completeOnboarding,
  getOnboardingStatus,
  saveOnboardingMaterials,
} from "@/lib/onboarding-api";
import {
  setOwnLearnerProfile,
  type LearnerProfile,
} from "@/lib/profile-api";

const STAGES = [
  { label: "Middle school", hint: "Build strong foundations" },
  { label: "High school", hint: "Prepare for exams and further study" },
  { label: "Undergraduate", hint: "Study courses and projects" },
  { label: "Graduate", hint: "Go deeper into research topics" },
  { label: "Professional or self-study", hint: "Learn for work or curiosity" },
  { label: "Other", hint: "Use a stage that fits you" },
] as const;

const EXPLANATION_STYLES = [
  {
    label: "Examples first, then principles",
    hint: "Start with a concrete example, then explain the rule",
  },
  {
    label: "Principles first, then examples",
    hint: "Explain the concept, then show how it works",
  },
  { label: "Step-by-step detail", hint: "Break the answer into small steps" },
  { label: "Concise and direct", hint: "Focus on the answer and key points" },
] as const;

const GOAL_SUGGESTIONS = [
  "Prepare for an exam",
  "Build a solid foundation",
  "Complete a project",
  "Explore a new subject",
] as const;

const MATERIAL_ACCEPT = ".txt,.md,.markdown,.pdf";
const MAX_MATERIAL_BYTES = 20 * 1024 * 1024;

export default function OnboardingPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(0);
  const [stage, setStage] = useState("");
  const [goal, setGoal] = useState("");
  const [explanationStyle, setExplanationStyle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [userId, setUserId] = useState("");
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const auth = await fetchAuthStatus();
      if (cancelled) return;
      if (!auth?.enabled) {
        router.replace("/chat");
        return;
      }
      if (!auth.authenticated) {
        router.replace("/login?next=/onboarding");
        return;
      }

      try {
        const onboarding = await getOnboardingStatus();
        if (cancelled) return;
        if (!onboarding.available || onboarding.completed) {
          router.replace("/chat");
          return;
        }
        const profile = onboarding.learner_profile ?? {};
        setStage(profile.grade_level ?? "");
        setGoal(profile.learning_goal ?? "");
        setExplanationStyle(profile.explanation_style ?? "");
        setUserId(auth.user_id ?? "");
        setReady(true);
      } catch {
        if (!cancelled) {
          setError(t("Could not load your onboarding status. Please try again."));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  function selectFiles(incoming: FileList | null) {
    if (!incoming?.length) return;
    const next: File[] = [];
    for (const file of Array.from(incoming)) {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
      const supported = [".txt", ".md", ".markdown", ".pdf"].includes(extension);
      if (!supported) {
        setError(t("Only TXT, Markdown, and PDF files are supported."));
        return;
      }
      if (file.size > MAX_MATERIAL_BYTES) {
        setError(t("Each material must be 20 MB or smaller."));
        return;
      }
      next.push(file);
    }
    setError("");
    setFiles((current) => [...current, ...next]);
  }

  async function finish(skip = false) {
    setSaving(true);
    setError("");

    if (!skip) {
      const profile: LearnerProfile = {};
      if (stage.trim()) profile.grade_level = stage.trim();
      if (goal.trim()) profile.learning_goal = goal.trim();
      if (explanationStyle) profile.explanation_style = explanationStyle;

      if (Object.keys(profile).length > 0) {
        try {
          await setOwnLearnerProfile(profile);
        } catch {
          setError(t("We couldn't save your learning profile. Please try again."));
          setSaving(false);
          return;
        }
      }

      if (files.length > 0) {
        try {
          await saveOnboardingMaterials(files, userId);
        } catch {
          setError(
            t("We couldn't upload your materials. You can retry or skip for now."),
          );
          setSaving(false);
          return;
        }
      }
    }

    try {
      await completeOnboarding();
      router.replace("/chat");
    } catch {
      setError(t("We couldn't complete setup. Please try again."));
      setSaving(false);
    }
  }

  if (!ready) {
    return (
      <div className="w-full max-w-sm px-6 text-center">
        {error ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        ) : (
          <div className="text-sm text-[var(--muted-foreground)]">
            {t("Loading your setup…")}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl px-4 py-8 sm:px-6">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm">
          <BookOpen size={21} />
        </div>
        <h1 className="font-serif text-2xl font-semibold tracking-tight text-[var(--foreground)]">
          {t("Welcome to TeachX")}
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--muted-foreground)]">
          {t(
            "Tell TeachX how you learn. This takes about a minute, and you can change everything later.",
          )}
        </p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4 sm:px-7">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
              {t("Learning setup")}
            </p>
            <p className="mt-0.5 text-sm text-[var(--foreground)]">
              {t("Step {{current}} of {{total}}", {
                current: step + 1,
                total: 3,
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void finish(true)}
            disabled={saving}
            className="rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)] disabled:opacity-50"
          >
            {t("Skip for now")}
          </button>
        </div>

        <div className="h-1 bg-[var(--muted)]">
          <div
            className="h-full bg-[var(--primary)] transition-all duration-300"
            style={{ width: `${((step + 1) / 3) * 100}%` }}
          />
        </div>

        <div className="px-5 py-6 sm:px-8 sm:py-8">
          {step === 0 && (
            <section>
              <div className="mb-5 flex items-start gap-3">
                <div className="mt-0.5 rounded-lg bg-blue-500/10 p-2 text-blue-600 dark:text-blue-400">
                  <BookOpen size={18} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-[var(--foreground)]">
                    {t("Which stage are you studying at?")}
                  </h2>
                  <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                    {t(
                      "Choose the closest match so explanations start at the right level.",
                    )}
                  </p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {STAGES.map((item) => {
                  const label = t(item.label);
                  const selected = stage === label;
                  return (
                    <button
                      key={item.label}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setStage(label)}
                      className={`flex items-start justify-between rounded-xl border px-4 py-3 text-left transition-colors ${
                        selected
                          ? "border-[var(--primary)] bg-[var(--primary)]/5"
                          : "border-[var(--border)] hover:border-[var(--primary)]/50"
                      }`}
                    >
                      <span>
                        <span className="block text-sm font-medium text-[var(--foreground)]">
                          {label}
                        </span>
                        <span className="mt-0.5 block text-xs text-[var(--muted-foreground)]">
                          {t(item.hint)}
                        </span>
                      </span>
                      {selected && (
                        <Check
                          size={17}
                          className="mt-0.5 shrink-0 text-[var(--primary)]"
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {step === 1 && (
            <section>
              <div className="mb-5 flex items-start gap-3">
                <div className="mt-0.5 rounded-lg bg-emerald-500/10 p-2 text-emerald-600 dark:text-emerald-400">
                  <Target size={18} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-[var(--foreground)]">
                    {t("What do you want to achieve?")}
                  </h2>
                  <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                    {t(
                      "Describe one or more goals so TeachX can keep answers focused.",
                    )}
                  </p>
                </div>
              </div>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={4}
                maxLength={160}
                placeholder={t("Example: Prepare for calculus finals")}
                className="w-full resize-none rounded-xl border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm leading-6 text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] focus:ring-2 focus:ring-[var(--primary)]"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                {GOAL_SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setGoal(t(suggestion))}
                    className="rounded-full border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--muted-foreground)] transition-colors hover:border-[var(--primary)]/50 hover:text-[var(--foreground)]"
                  >
                    {t(suggestion)}
                  </button>
                ))}
              </div>
            </section>
          )}

          {step === 2 && (
            <section className="space-y-7">
              <div>
                <div className="mb-5 flex items-start gap-3">
                  <div className="mt-0.5 rounded-lg bg-violet-500/10 p-2 text-violet-600 dark:text-violet-400">
                    <MessageSquareText size={18} />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-[var(--foreground)]">
                      {t("How should TeachX explain things?")}
                    </h2>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                      {t(
                        "You can choose a default and change it in your profile at any time.",
                      )}
                    </p>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {EXPLANATION_STYLES.map((item) => {
                    const label = t(item.label);
                    const selected = explanationStyle === label;
                    return (
                      <button
                        key={item.label}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => setExplanationStyle(label)}
                        className={`flex items-start justify-between rounded-xl border px-4 py-3 text-left transition-colors ${
                          selected
                            ? "border-[var(--primary)] bg-[var(--primary)]/5"
                            : "border-[var(--border)] hover:border-[var(--primary)]/50"
                        }`}
                      >
                        <span>
                          <span className="block text-sm font-medium text-[var(--foreground)]">
                            {label}
                          </span>
                          <span className="mt-0.5 block text-xs text-[var(--muted-foreground)]">
                            {t(item.hint)}
                          </span>
                        </span>
                        {selected && (
                          <Check
                            size={17}
                            className="mt-0.5 shrink-0 text-[var(--primary)]"
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold text-[var(--foreground)]">
                      {t("Add your first material")}{" "}
                      <span className="font-normal text-[var(--muted-foreground)]">
                        ({t("Optional")})
                      </span>
                    </h2>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                      {t(
                        "Upload notes, textbook chapters, or PDFs so future answers can cite them.",
                      )}
                    </p>
                  </div>
                  <FileText
                    size={20}
                    className="mt-1 shrink-0 text-[var(--muted-foreground)]"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border)] bg-[var(--background)] px-4 py-5 text-sm text-[var(--muted-foreground)] transition-colors hover:border-[var(--primary)]/60 hover:text-[var(--foreground)]"
                >
                  <Upload size={17} />
                  {t("Choose files")}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={MATERIAL_ACCEPT}
                  onChange={(event) => selectFiles(event.target.files)}
                  className="hidden"
                />
                <p className="mt-2 text-xs text-[var(--muted-foreground)]">
                  {t("TXT, Markdown, or PDF · Up to 20 MB each")}
                </p>
                {files.length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="text-xs text-[var(--muted-foreground)]">
                      {t("Selected files: {{count}}", { count: files.length })}
                    </p>
                    {files.map((file) => (
                      <div
                        key={`${file.name}-${file.lastModified}`}
                        className="flex items-center justify-between gap-3 rounded-lg bg-[var(--muted)] px-3 py-2 text-sm"
                      >
                        <span className="min-w-0 truncate text-[var(--foreground)]">
                          {file.name}
                        </span>
                        <button
                          type="button"
                          aria-label={t("Remove file")}
                          onClick={() =>
                            setFiles((current) =>
                              current.filter((item) => item !== file),
                            )
                          }
                          className="shrink-0 text-[var(--muted-foreground)] hover:text-red-500"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {error && (
            <div className="mt-5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-[var(--border)] bg-[var(--muted)]/20 px-5 py-4 sm:px-8">
          <button
            type="button"
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={step === 0 || saving}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)] disabled:invisible"
          >
            <ArrowLeft size={15} />
            {t("Back")}
          </button>
          {step < 2 ? (
            <button
              type="button"
              onClick={() => setStep((current) => Math.min(2, current + 1))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2.5 text-sm font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90"
            >
              {t("Continue")}
              <ArrowRight size={15} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void finish(false)}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-4 py-2.5 text-sm font-medium text-[var(--primary-foreground)] transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {saving ? t("Saving your setup…") : t("Finish setup")}
              {!saving && <ArrowRight size={15} />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
