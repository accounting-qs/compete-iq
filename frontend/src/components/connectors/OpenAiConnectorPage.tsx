"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchOpenAiStatus,
  saveOpenAiApiKey,
  deleteOpenAiApiKey,
  type OpenAiCredentialStatus,
} from "@/lib/api";

export function OpenAiConnectorPage() {
  const [status, setStatus] = useState<OpenAiCredentialStatus | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  useEffect(() => {
    fetchOpenAiStatus()
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load OpenAI status"))
      .finally(() => setLoadingStatus(false));
  }, []);

  async function handleSave() {
    setError(null); setMessage(null); setSaving(true);
    try {
      const s = await saveOpenAiApiKey(apiKeyInput.trim());
      setStatus(s);
      setApiKeyInput("");
      setMessage("OpenAI API key saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save OpenAI key");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove OpenAI API key? Case-study URL imports will stop working until you reconnect.")) return;
    try {
      await deleteOpenAiApiKey();
      setStatus({ configured: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete OpenAI key");
    }
  }

  if (loadingStatus) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

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
        <div className="w-8 h-8 rounded-md bg-emerald-500/15 flex items-center justify-center">
          <svg className="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">
          OpenAI
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
        <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-1">OpenAI API</h2>
        <p className="text-xs text-zinc-500 mb-4">
          Used to extract structured fields when you import a case study from a URL.
          We use <span className="font-mono">gpt-4o-mini</span> (~$0.0002 per import).
          Your key is stored on the server and used only for importer requests.
        </p>

        {status?.configured ? (
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">API Key</label>
              <div className="font-mono text-xs text-zinc-700 dark:text-zinc-300">{status.api_key_masked}</div>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold border bg-emerald-500/15 text-emerald-500 border-emerald-500/30">
              Connected
            </span>
            <button
              onClick={handleDelete}
              className="px-3 py-1.5 text-xs rounded-md border border-red-500/40 text-red-500 hover:bg-red-500/10"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
              OpenAI API Key (sk-…)
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="Paste your API key"
                className="flex-1 bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
              <button
                onClick={handleSave}
                disabled={!apiKeyInput.trim() || saving}
                className="px-3 py-1.5 text-xs rounded-md bg-violet-600 hover:bg-violet-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? "Saving..." : "Save & Verify"}
              </button>
            </div>
            <p className="text-[11px] text-zinc-500">
              Get a key from{" "}
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noreferrer noopener"
                className="text-violet-500 hover:text-violet-400"
              >
                platform.openai.com/api-keys
              </a>
              .
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
