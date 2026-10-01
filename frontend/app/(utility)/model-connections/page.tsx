"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Cable,
  CheckCircle2,
  KeyRound,
  Pencil,
  PlugZap,
  RefreshCcw,
  Server,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  activateModelConnection,
  activatePlatformDefaultModel,
  deleteModelConnection,
  listModelConnections,
  saveModelConnection,
  testModelConnection,
  type ModelConnection,
  type ModelConnectionList,
} from "@/lib/model-connections-api";
import { notify } from "@/lib/notifications";

interface FormState {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  default_model: string;
  models: string[];
}

const PRESETS = [
  {
    id: "deepseek",
    label: "DeepSeek",
    name: "DeepSeek Flash",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-flash",
    models: ["deepseek-flash", "deepseek-v4-pro"],
  },
  {
    id: "openai",
    label: "OpenAI",
    name: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    models: [],
  },
  {
    id: "custom",
    label: "OpenAI-compatible platform",
    name: "Custom provider",
    baseUrl: "",
    model: "",
    models: [],
  },
] as const;

const EMPTY_FORM: FormState = {
  id: "",
  name: "DeepSeek Flash",
  base_url: "https://api.deepseek.com/v1",
  api_key: "",
  default_model: "deepseek-flash",
  models: ["deepseek-flash", "deepseek-v4-pro"],
};

export default function ModelConnectionsPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<ModelConnectionList | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [preset, setPreset] = useState("deepseek");
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setData(await listModelConnections());
  }, []);

  useEffect(() => {
    let cancelled = false;
    void load()
      .catch(() => {
        if (!cancelled) setError(t("Could not load model connections"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [load, t]);

  const hasActiveConnection = useMemo(
    () => Boolean(data?.connections.some((connection) => connection.active)),
    [data],
  );

  function applyPreset(id: string) {
    const next = PRESETS.find((item) => item.id === id) ?? PRESETS[0];
    setPreset(id);
    setForm((current) => ({
      ...current,
      name: next.name,
      base_url: next.baseUrl,
      default_model: next.model,
      models: [...next.models],
    }));
  }

  function edit(connection: ModelConnection) {
    setPreset("custom");
    setForm({
      id: connection.id,
      name: connection.name,
      base_url: connection.base_url,
      api_key: "",
      default_model: connection.default_model,
      models: connection.models,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function test() {
    setTesting(true);
    setError("");
    try {
      const models = await testModelConnection({
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        connection_id: form.id || undefined,
      });
      setForm((current) => ({
        ...current,
        models,
        default_model: models.includes(current.default_model)
          ? current.default_model
          : models[0] ?? current.default_model,
      }));
      notify(t("Loaded {{count}} models", { count: models.length }), {
        tone: "success",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("Connection test failed"));
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await saveModelConnection({
        id: form.id || undefined,
        name: form.name,
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        default_model: form.default_model,
        models: form.models,
      });
      await load();
      setForm(EMPTY_FORM);
      setPreset("deepseek");
      notify(t("Model connection saved"), { tone: "success" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("Could not save model connection"));
    } finally {
      setSaving(false);
    }
  }

  async function activate(connectionId: string) {
    setBusyId(connectionId);
    try {
      await activateModelConnection(connectionId);
      await load();
      notify(t("Model connection activated"), { tone: "success" });
    } catch (cause) {
      notify(cause instanceof Error ? cause.message : t("Action failed"), {
        tone: "error",
      });
    } finally {
      setBusyId("");
    }
  }

  async function useDefault() {
    try {
      await activatePlatformDefaultModel();
      await load();
      notify(t("Platform default activated"), { tone: "success" });
    } catch (cause) {
      notify(cause instanceof Error ? cause.message : t("Action failed"), {
        tone: "error",
      });
    }
  }

  async function remove(connection: ModelConnection) {
    if (!window.confirm(t("Delete model connection {{name}}?", { name: connection.name }))) {
      return;
    }
    setBusyId(connection.id);
    try {
      await deleteModelConnection(connection.id);
      await load();
      if (form.id === connection.id) setForm(EMPTY_FORM);
      notify(t("Model connection deleted"), { tone: "success" });
    } catch (cause) {
      notify(cause instanceof Error ? cause.message : t("Action failed"), {
        tone: "error",
      });
    } finally {
      setBusyId("");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 text-sm text-[var(--muted-foreground)] sm:px-6">
        {t("Loading model connections…")}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-7 sm:px-6">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-cyan-500/10 p-2.5 text-cyan-600 dark:text-cyan-400">
          <Cable size={22} />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--foreground)]">
            {t("Model connections")}
          </h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
            {t(
              "Choose the TeachX default or connect your own OpenAI-compatible platform. API keys are encrypted before they are stored and are never returned to the browser.",
            )}
          </p>
        </div>
      </div>

      {error ? (
        <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      ) : null}

      <section className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Server size={19} className="mt-0.5 text-[var(--muted-foreground)]" />
            <div>
              <h2 className="text-sm font-semibold text-[var(--foreground)]">
                {t("TeachX platform default")}
              </h2>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                {data?.platform_default.provider} · {data?.platform_default.model}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void useDefault()}
            disabled={!hasActiveConnection}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--foreground)] hover:bg-[var(--muted)] disabled:opacity-40"
          >
            {!hasActiveConnection ? <CheckCircle2 size={14} /> : <RefreshCcw size={14} />}
            {hasActiveConnection ? t("Use platform default") : t("Currently active")}
          </button>
        </div>
      </section>

      <section className="mt-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm sm:p-6">
        <div className="flex items-center gap-2">
          <PlugZap size={18} className="text-[var(--primary)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">
            {form.id ? t("Edit model connection") : t("Add model connection")}
          </h2>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="text-xs text-[var(--muted-foreground)]">
            {t("Platform preset")}
            <select
              value={preset}
              onChange={(event) => applyPreset(event.target.value)}
              disabled={Boolean(form.id)}
              className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] disabled:opacity-60"
            >
              {PRESETS.map((item) => (
                <option key={item.id} value={item.id}>
                  {t(item.label)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-[var(--muted-foreground)]">
            {t("Connection name")}
            <input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
            />
          </label>
          <label className="text-xs text-[var(--muted-foreground)] sm:col-span-2">
            {t("Base URL")}
            <input
              value={form.base_url}
              onChange={(event) => setForm({ ...form, base_url: event.target.value })}
              placeholder={t("Base URL placeholder")}
              className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
            />
          </label>
          <label className="text-xs text-[var(--muted-foreground)]">
            {t("API Key")}
            <div className="relative mt-1.5">
              <KeyRound
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
              />
              <input
                type="password"
                value={form.api_key}
                onChange={(event) => setForm({ ...form, api_key: event.target.value })}
                autoComplete="new-password"
                placeholder={form.id && form.api_key === "" ? t("Leave blank to keep saved key") : t("Enter API key")}
                className="block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] py-2 pl-9 pr-3 text-sm text-[var(--foreground)]"
              />
            </div>
          </label>
          <label className="text-xs text-[var(--muted-foreground)]">
            {t("Default model")}
            {form.models.length ? (
              <select
                value={form.default_model}
                onChange={(event) => setForm({ ...form, default_model: event.target.value })}
                className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
              >
                {form.models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={form.default_model}
                onChange={(event) => setForm({ ...form, default_model: event.target.value })}
                placeholder={t("Model ID placeholder")}
                className="mt-1.5 block w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)]"
              />
            )}
          </label>
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {form.id ? (
            <button
              type="button"
              onClick={() => {
                setForm(EMPTY_FORM);
                setPreset("deepseek");
              }}
              className="rounded-lg px-3 py-2 text-sm text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
            >
              {t("Cancel")}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void test()}
            disabled={testing || !form.base_url}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3.5 py-2 text-sm font-medium text-[var(--foreground)] hover:bg-[var(--muted)] disabled:opacity-50"
          >
            <RefreshCcw size={15} className={testing ? "animate-spin" : ""} />
            {testing ? t("Testing…") : t("Test connection")}
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || !form.name || !form.base_url || !form.default_model}
            className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
          >
            {saving ? t("Saving…") : t("Save connection")}
          </button>
        </div>
      </section>

      <section className="mt-5">
        <h2 className="text-sm font-semibold text-[var(--foreground)]">
          {t("Your model connections")}
        </h2>
        {data?.connections.length ? (
          <div className="mt-3 space-y-3">
            {data.connections.map((connection) => (
              <article
                key={connection.id}
                className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-[var(--foreground)]">
                      {connection.name}
                    </span>
                    {connection.active ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 size={11} />
                        {t("Active")}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 truncate text-xs text-[var(--muted-foreground)]">
                    {connection.base_url} · {connection.default_model}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {!connection.active ? (
                    <button
                      type="button"
                      onClick={() => void activate(connection.id)}
                      disabled={busyId === connection.id}
                      className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] hover:bg-[var(--muted)] disabled:opacity-50"
                    >
                      {t("Use this model")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => edit(connection)}
                    aria-label={t("Edit")}
                    className="rounded-lg p-2 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(connection)}
                    disabled={busyId === connection.id}
                    aria-label={t("Delete")}
                    className="rounded-lg p-2 text-[var(--muted-foreground)] hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="mt-3 rounded-2xl border border-dashed border-[var(--border)] px-5 py-8 text-center text-sm text-[var(--muted-foreground)]">
            {t("No personal model connections yet. TeachX will use the platform default.")}
          </div>
        )}
      </section>
    </div>
  );
}
