"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchAuthStatus } from "@/lib/auth";
import { getOnboardingStatus } from "@/lib/onboarding-api";

/** Keep newly registered accounts in the first-run flow until they finish or skip it. */
export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      let redirecting = false;
      try {
        const auth = await fetchAuthStatus();
        if (cancelled || !auth?.enabled || !auth.authenticated) return;

        if (auth.onboarding_completed === false) {
          redirecting = true;
          router.replace("/onboarding");
          return;
        }
        if (auth.onboarding_completed === true) return;

        try {
          const onboarding = await getOnboardingStatus();
          if (!cancelled && !onboarding.completed) {
            redirecting = true;
            router.replace("/onboarding");
          }
        } catch {
          // Onboarding must never make chat unavailable when the status API is down.
        }
      } finally {
        if (!cancelled && !redirecting) setChecking(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router]);

  if (checking) {
    return <div aria-busy="true" className="min-h-dvh bg-[var(--background)]" />;
  }
  return children;
}
