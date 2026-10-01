import { apiFetch, apiUrl } from "@/lib/api";

export interface PlatformDefaultModel {
  provider: string;
  model: string;
  base_url: string;
}

export interface ModelConnection {
  id: string;
  name: string;
  base_url: string;
  default_model: string;
  models: string[];
  active: boolean;
  has_api_key: boolean;
  created_at: number;
  updated_at: number;
}

export interface ModelConnectionList {
  platform_default: PlatformDefaultModel;
  connections: ModelConnection[];
}

export interface ModelConnectionInput {
  id?: string;
  name: string;
  base_url: string;
  api_key?: string;
  default_model: string;
  models: string[];
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // Use the stable fallback.
  }
  return fallback;
}

export async function listModelConnections(): Promise<ModelConnectionList> {
  const response = await apiFetch(apiUrl("/api/model-connections"), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load model connections"));
  }
  return (await response.json()) as ModelConnectionList;
}

export async function testModelConnection(input: {
  base_url: string;
  api_key?: string;
  connection_id?: string;
}): Promise<string[]> {
  const response = await apiFetch(apiUrl("/api/model-connections/test"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Connection test failed"));
  }
  const body = (await response.json()) as { models?: string[] };
  return Array.isArray(body.models) ? body.models : [];
}

export async function saveModelConnection(
  input: ModelConnectionInput,
): Promise<ModelConnection> {
  const response = await apiFetch(apiUrl("/api/model-connections"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to save model connection"));
  }
  const body = (await response.json()) as { connection: ModelConnection };
  return body.connection;
}

export async function activateModelConnection(connectionId: string): Promise<void> {
  const response = await apiFetch(
    apiUrl(`/api/model-connections/${encodeURIComponent(connectionId)}/activate`),
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to activate model connection"));
  }
}

export async function activatePlatformDefaultModel(): Promise<void> {
  const response = await apiFetch(apiUrl("/api/model-connections/default/activate"), {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to activate default model"));
  }
}

export async function deleteModelConnection(connectionId: string): Promise<void> {
  const response = await apiFetch(
    apiUrl(`/api/model-connections/${encodeURIComponent(connectionId)}`),
    { method: "DELETE" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to delete model connection"));
  }
}
