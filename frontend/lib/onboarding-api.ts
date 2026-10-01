import { apiFetch, apiUrl } from "@/lib/api";
import { invalidateAuthStatusCache } from "@/lib/auth";
import type { LearnerProfile } from "@/lib/profile-api";

export interface OnboardingStatus {
  available: boolean;
  completed: boolean;
  learner_profile: LearnerProfile | null;
}

async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // The response was not JSON; the caller gets the localized fallback.
  }
  return fallback;
}

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const response = await apiFetch(apiUrl("/api/auth/onboarding"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to load onboarding status"));
  }
  return (await response.json()) as OnboardingStatus;
}

export async function completeOnboarding(): Promise<void> {
  const response = await apiFetch(apiUrl("/api/auth/onboarding/complete"), {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to complete onboarding"));
  }
  invalidateAuthStatusCache();
}

function appendFiles(form: FormData, files: File[]): void {
  for (const file of files) {
    form.append("files", file);
    form.append("rel_paths", file.webkitRelativePath || "");
  }
}

/**
 * Store the optional first material in a deterministic, user-scoped knowledge
 * base. Retrying after a partial upload reuses the existing base.
 */
export async function saveOnboardingMaterials(
  files: File[],
  userKey: string,
): Promise<void> {
  if (files.length === 0) return;

  const scope = userKey.replace(/[^\w-]/g, "").slice(0, 16) || "learner";
  const name = `学习资料-${scope}`;
  const listResponse = await apiFetch(apiUrl("/api/knowledge-bases"), {
    cache: "no-store",
  });
  if (!listResponse.ok) {
    throw new Error(
      await errorDetail(listResponse, "Failed to inspect knowledge bases"),
    );
  }
  const listBody = (await listResponse.json()) as {
    knowledge_bases?: Array<{ name?: string }>;
  };
  const exists = listBody.knowledge_bases?.some((base) => base.name === name);

  const form = new FormData();
  appendFiles(form, files);
  if (exists) {
    const response = await apiFetch(
      apiUrl(`/api/knowledge-bases/${encodeURIComponent(name)}/upload`),
      { method: "POST", body: form },
    );
    if (!response.ok) {
      throw new Error(await errorDetail(response, "Failed to upload materials"));
    }
    return;
  }

  form.append("name", name);
  form.append("rag_provider", "sqlite-fts");
  const response = await apiFetch(apiUrl("/api/knowledge-bases"), {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to upload materials"));
  }
}
