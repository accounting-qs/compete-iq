"use client";

import { useEffect, useState } from "react";
import {
  fetchWgStatus,
  saveWgApiKey,
  deleteWgApiKey,
  fetchWgWebinars,
  refreshWgWebinars,
  syncWgSubscribers,
  type WgCredentialStatus,
  type WgWebinar,
} from "@/lib/api";

export function ConnectorsPage() {
  const [status, setStatus] = useState<WgCredentialStatus | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [webinars, setWebinars] = useState<WgWebinar[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function loadAll() {
    setLoading(true);
    try {
      const s = await fetchWgStatus();
      setStatus(s);
      if (s.configured) {
        const { webinars } = await fetchWgWebinars();
        setWebinars(webinars);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleSave() {
    setError(null);
    setMessage(null);
    setSaving(true);
    try {
      const s = await saveWgApiKey(apiKeyInput.trim());
      setStatus(s);
      setApiKeyInput("");
      setMessage("API key saved.");
      // Auto-refresh webinars on first save
      await handleRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove WebinarGeek API key? Synced data will be preserved.")) return;
    setError(null);
    try {
      await deleteWgApiKey();
      setStatus({ configured: false });
      setWebinars([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  }

  async function handleRefresh() {
    setError(null);
    setMessage(null);
    setRefreshing(true);
    try {
      const { count } = await refreshWgWebinars();
      const { webinars } = await fetchWgWebinars();
      setWebinars(webinars);
      setMessage(`Refreshed — ${count} broadcasts loaded.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleSync(broadcastId: string) {
    setError(null);
    setMessage(null);
    setSyncingId(broadcastId);
    try {
      const res = await syncWgSubscribers(broadcastId);
      setMessage(`Synced ${res.total} subscribers for ${broadcastId}.`);
      const { webinars } = await fetchWgWebinars();
      setWebinars(webinars);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to sync");
    } finally {
      setSyncingId(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-zinc-500">Loading connectors...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="px-6 py-6 max-w-5xl">
      <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 tracking-tight mb-6">
        Connectors
      </h1>

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

      {/* ── WebinarGeek card ────────────────────────────────────────── */}
      <section className="rounded-lg border border-zinc-200 dark:border-zinc-800/60 bg-white dark:bg-zinc-900/40 overflow-hidden">
        <header className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800/60 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">WebinarGeek</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              Connect your API key to sync webinar subscribers.
            </p>
          </div>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
              status?.configured
                ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/30"
                : "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"
            }`}
          >
            {status?.configured ? "Connected" : "Not connected"}
          </span>
        </header>

        <div className="p-4 space-y-4">
          {/* API key row */}
          {status?.configured ? (
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                  API Key
                </label>
                <div className="font-mono text-xs text-zinc-700 dark:text-zinc-300">
                  {status.api_key_masked}
                </div>
              </div>
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
                WebinarGeek API Key
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
            </div>
          )}

          {/* Webinars list */}
          {status?.configured && (
            <div className="pt-2 border-t border-zinc-200 dark:border-zinc-800/60">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  Cached broadcasts ({webinars.length})
                </h3>
                <button
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="px-3 py-1.5 text-xs rounded-md border border-zinc-300 dark:border-zinc-700/60 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 disabled:opacity-50"
                >
                  {refreshing ? "Refreshing..." : "Refresh from WebinarGeek"}
                </button>
              </div>

              {webinars.length === 0 ? (
                <p className="text-xs text-zinc-500 py-4 text-center">
                  No broadcasts cached yet. Click "Refresh" to pull from WebinarGeek.
                </p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-200 dark:border-zinc-800/60 text-zinc-500 text-[10px] uppercase tracking-wider">
                      <th className="text-left py-2 px-2 font-semibold">Name</th>
                      <th className="text-left py-2 px-2 font-semibold">Broadcast ID</th>
                      <th className="text-left py-2 px-2 font-semibold">Starts</th>
                      <th className="text-right py-2 px-2 font-semibold">Subs</th>
                      <th className="text-left py-2 px-2 font-semibold">Last synced</th>
                      <th className="text-right py-2 px-2 font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {webinars.map((w) => (
                      <tr
                        key={w.broadcast_id}
                        className="border-b border-zinc-100 dark:border-zinc-800/30 hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                      >
                        <td className="py-2 px-2 text-zinc-800 dark:text-zinc-200">{w.name}</td>
                        <td className="py-2 px-2 font-mono text-zinc-500">{w.broadcast_id}</td>
                        <td className="py-2 px-2 text-zinc-600 dark:text-zinc-400">
                          {w.starts_at ? new Date(w.starts_at).toLocaleString() : "—"}
                        </td>
                        <td className="py-2 px-2 text-right font-mono">{w.subscriber_count}</td>
                        <td className="py-2 px-2 text-zinc-500">
                          {w.last_synced_at ? new Date(w.last_synced_at).toLocaleString() : "Never"}
                        </td>
                        <td className="py-2 px-2 text-right">
                          <button
                            onClick={() => handleSync(w.broadcast_id)}
                            disabled={syncingId === w.broadcast_id}
                            className="px-2.5 py-1 text-[11px] rounded-md bg-violet-600 hover:bg-violet-500 text-white font-semibold disabled:opacity-50"
                          >
                            {syncingId === w.broadcast_id ? "Syncing..." : "Sync"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
