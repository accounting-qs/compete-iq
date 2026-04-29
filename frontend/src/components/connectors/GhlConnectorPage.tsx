"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchGhlConnectorStatus,
  saveGhlConnector,
  deleteGhlConnector,
  type GhlCredentialStatus,
} from "@/lib/api";

export function GhlConnectorPage() {
  const [status, setStatus] = useState<GhlCredentialStatus | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [locationIdInput, setLocationIdInput] = useState("");
  const [pipelineIdInput, setPipelineIdInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  useEffect(() => {
    fetchGhlConnectorStatus()
      .then((s) => {
        setStatus(s);
        if (s.configured && s.location_id) setLocationIdInput(s.location_id);
        if (s.configured && s.pipeline_id) setPipelineIdInput(s.pipeline_id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load GHL status"))
      .finally(() => setLoadingStatus(false));
  }, []);

  async function handleSave() {
    setError(null);
    setMessage(null);
    setSaving(true);
    try {
      const s = await saveGhlConnector(
        apiKeyInput.trim(),
        locationIdInput.trim(),
        pipelineIdInput.trim() || null,
      );
      setStatus(s);
      setApiKeyInput("");
      setMessage("GHL credentials saved and verified.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save GHL credentials");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove GHL credentials? Sync will fail until you reconnect (or env-var fallback is in place).")) return;
    try {
      await deleteGhlConnector();
      const s = await fetchGhlConnectorStatus();
      setStatus(s);
      setLocationIdInput(s.location_id ?? "");
      setPipelineIdInput(s.pipeline_id ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete GHL credentials");
    }
  }

  if (loadingStatus) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const showForm = !status?.configured || status?.source === "env";

  return (
    <div className="px-6 py-6 max-w-[1400px]">
      <div className="flex items-center gap-3 mb-6">
        <Link
          href="/connectors"
          className="text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 text-lg"
          aria-label="Back to connectors"
        >
          ←
        </Link>
        <div className="w-8 h-8 rounded-md bg-amber-500/15 flex items-center justify-center">
          <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">
          GoHighLevel
        </h1>
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 rounded-md border border-red-500/30 bg-red-500/10 text-xs text-red-500">
          {error}
        </div>
      )}
      {message && (
        <div className="mb-4 px-3 py-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-500">
          {message}
        </div>
      )}

      <section className="rounded-lg border border-zinc-200 dark:border-zinc-800/60 bg-white dark:bg-zinc-900/40 p-4">
        <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-1">GHL API credentials</h2>
        <p className="text-xs text-zinc-500 mb-4">
          Used by the Sync engine to pull contacts and opportunities into the local DB
          (Statistics dashboard, per-webinar metrics). The connector verifies your credentials
          against <span className="font-mono">GET /locations/{"{id}"}</span> before saving.
        </p>

        {status?.configured && status?.source === "db" && (
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">API Key</label>
                <div className="font-mono text-xs text-zinc-700 dark:text-zinc-300 truncate">{status.api_key_masked}</div>
              </div>
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Location ID</label>
                <div className="font-mono text-xs text-zinc-700 dark:text-zinc-300 truncate">{status.location_id}</div>
              </div>
              <div className="flex-1 min-w-0">
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Pipeline ID</label>
                <div className="font-mono text-xs text-zinc-700 dark:text-zinc-300 truncate">
                  {status.pipeline_id || <span className="text-zinc-500 italic">not set</span>}
                </div>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold border bg-emerald-500/15 text-emerald-500 border-emerald-500/30 whitespace-nowrap">
                Connected
              </span>
              <button
                onClick={handleDelete}
                className="px-3 py-1.5 text-xs rounded-md border border-red-500/40 text-red-500 hover:bg-red-500/10"
              >
                Remove
              </button>
            </div>
          </div>
        )}

        {status?.configured && status?.source === "env" && (
          <div className="mb-4 px-3 py-2 rounded-md border border-amber-500/30 bg-amber-500/10 text-xs text-amber-500">
            Credentials are currently loaded from environment variables (<span className="font-mono">GHL_API_KEY</span>,{" "}
            <span className="font-mono">GHL_LOCATION_ID</span>). Saving below moves them into the
            database — they take precedence over env vars from then on.
          </div>
        )}

        {showForm && (
          <div className="space-y-3">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                API Key (Private Integration Token, <span className="font-mono">pit-…</span>)
              </label>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="Paste your GHL private integration token"
                className="w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                Location ID
              </label>
              <input
                type="text"
                value={locationIdInput}
                onChange={(e) => setLocationIdInput(e.target.value)}
                placeholder="e.g. G7ZOWCq78JrzUjlLMCxt"
                className="w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-xs font-mono text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                Pipeline ID <span className="text-zinc-500 normal-case font-normal">(optional — required for opportunity sync)</span>
              </label>
              <input
                type="text"
                value={pipelineIdInput}
                onChange={(e) => setPipelineIdInput(e.target.value)}
                placeholder="e.g. zbI8YxmB9qhk1h4cInnq"
                className="w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-xs font-mono text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
            <div className="flex justify-end">
              <button
                onClick={handleSave}
                disabled={!apiKeyInput.trim() || !locationIdInput.trim() || saving}
                className="px-3 py-1.5 text-xs rounded-md bg-violet-600 hover:bg-violet-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? "Verifying…" : "Save & Verify"}
              </button>
            </div>
            <p className="text-[11px] text-zinc-500">
              Generate a Private Integration Token from your GHL agency settings → Private Integrations.
              The token must have <span className="font-mono">contacts.readonly</span> and{" "}
              <span className="font-mono">opportunities.readonly</span> scopes. Pipeline ID can be
              found in the URL when viewing a pipeline in GHL.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
