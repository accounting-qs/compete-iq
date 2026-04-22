"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchGhlSyncStatus,
  fetchGhlSyncHistory,
  triggerGhlSync,
  fetchGhlSyncSettings,
  updateGhlSyncSettings,
  type GhlSyncRun,
  type GhlSyncStatus,
  type GhlSyncSettings,
} from "@/lib/api";

const DAYS = [
  { value: "mon", label: "Mon" },
  { value: "tue", label: "Tue" },
  { value: "wed", label: "Wed" },
  { value: "thu", label: "Thu" },
  { value: "fri", label: "Fri" },
  { value: "sat", label: "Sat" },
  { value: "sun", label: "Sun" },
];

const INTERVAL_OPTIONS = [1, 2, 3, 6, 12, 24];

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-amber-500/15 text-amber-500 border-amber-500/30",
    completed: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
    failed: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${colors[status] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"}`}>
      {status}
    </span>
  );
}

export function SyncPage() {
  const [status, setStatus] = useState<GhlSyncStatus | null>(null);
  const [history, setHistory] = useState<GhlSyncRun[]>([]);
  const [settings, setSettings] = useState<GhlSyncSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set());
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [st, h, s] = await Promise.all([
        fetchGhlSyncStatus(),
        fetchGhlSyncHistory(50),
        fetchGhlSyncSettings(),
      ]);
      setStatus(st);
      setHistory(h.runs);
      setSettings(s);
    } catch (err) {
      console.error("Failed to load sync data:", err);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      await refresh();
      if (mounted) setLoading(false);
    })();
    return () => { mounted = false; };
  }, [refresh]);

  // Auto-poll while a sync is running
  useEffect(() => {
    if (status?.is_running) {
      pollRef.current = window.setInterval(refresh, 5000);
    } else if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [status?.is_running, refresh]);

  const handleTrigger = async (syncType: "full" | "incremental") => {
    if (triggering) return;
    setTriggering(true);
    try {
      await triggerGhlSync(syncType);
      await refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to trigger sync");
    } finally {
      setTriggering(false);
    }
  };

  const handleSettingsChange = async (patch: Partial<GhlSyncSettings>) => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const updated = await updateGhlSyncSettings(patch);
      setSettings(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSavingSettings(false);
    }
  };

  const toggleErrorExpand = (runId: string) => {
    setExpandedErrors((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-zinc-500">Loading sync status...</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Sticky header */}
      <div className="sticky top-12 z-40 bg-white dark:bg-zinc-950/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800/40 px-6 py-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">GHL Sync</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleTrigger("incremental")}
              disabled={triggering || status?.is_running}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Sync Incremental
            </button>
            <button
              onClick={() => handleTrigger("full")}
              disabled={triggering || status?.is_running}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Sync Full
            </button>
          </div>
        </div>
      </div>

      <div className="px-6 py-6 space-y-6 max-w-6xl">
        {/* Current status card */}
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-800/40 bg-zinc-50 dark:bg-zinc-900/40 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Current Status</h2>
            {status?.is_running && (
              <div className="flex items-center gap-2 text-xs text-amber-500">
                <div className="w-3 h-3 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                Sync in progress...
              </div>
            )}
          </div>
          {status?.latest ? (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
              <div>
                <div className="text-zinc-500 uppercase tracking-wider text-[10px] mb-0.5">Type</div>
                <div className="text-zinc-800 dark:text-zinc-200 font-medium">{status.latest.sync_type} ({status.latest.trigger})</div>
              </div>
              <div>
                <div className="text-zinc-500 uppercase tracking-wider text-[10px] mb-0.5">Status</div>
                <StatusPill status={status.latest.status} />
              </div>
              <div>
                <div className="text-zinc-500 uppercase tracking-wider text-[10px] mb-0.5">Started</div>
                <div className="text-zinc-800 dark:text-zinc-200">{formatTimestamp(status.latest.started_at)}</div>
              </div>
              <div>
                <div className="text-zinc-500 uppercase tracking-wider text-[10px] mb-0.5">Duration</div>
                <div className="text-zinc-800 dark:text-zinc-200 font-mono">{formatDuration(status.latest.duration_seconds)}</div>
              </div>
              <div>
                <div className="text-zinc-500 uppercase tracking-wider text-[10px] mb-0.5">Records</div>
                <div className="text-zinc-800 dark:text-zinc-200 font-mono">
                  {status.latest.contacts_synced.toLocaleString()}c · {status.latest.opportunities_synced.toLocaleString()}o
                  {status.latest.errors_count > 0 && (
                    <span className="text-red-400 ml-1">· {status.latest.errors_count}err</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">No syncs yet. Click "Sync Full" above to run the first one.</p>
          )}
        </div>

        {/* Settings panel */}
        {settings && (
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900/20 p-4">
            <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">Schedule Settings</h2>

            <div className="space-y-4">
              {/* Incremental */}
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={settings.incremental_enabled}
                    onChange={(e) => handleSettingsChange({ incremental_enabled: e.target.checked })}
                    disabled={savingSettings}
                    className="w-4 h-4"
                  />
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">Incremental sync</span>
                </label>
                <span className="text-zinc-500 text-xs">every</span>
                <select
                  value={settings.incremental_interval_hours}
                  onChange={(e) => handleSettingsChange({ incremental_interval_hours: parseInt(e.target.value) })}
                  disabled={savingSettings || !settings.incremental_enabled}
                  className="bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-2 py-1 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                >
                  {INTERVAL_OPTIONS.map((h) => (
                    <option key={h} value={h}>{h}h</option>
                  ))}
                </select>
              </div>

              {/* Weekly full */}
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={settings.weekly_full_enabled}
                    onChange={(e) => handleSettingsChange({ weekly_full_enabled: e.target.checked })}
                    disabled={savingSettings}
                    className="w-4 h-4"
                  />
                  <span className="font-semibold text-zinc-800 dark:text-zinc-200">Weekly full sync</span>
                </label>
                <span className="text-zinc-500 text-xs">on</span>
                <select
                  value={settings.weekly_full_day_of_week}
                  onChange={(e) => handleSettingsChange({ weekly_full_day_of_week: e.target.value })}
                  disabled={savingSettings || !settings.weekly_full_enabled}
                  className="bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-2 py-1 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                >
                  {DAYS.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
                <span className="text-zinc-500 text-xs">at</span>
                <select
                  value={settings.weekly_full_hour_local}
                  onChange={(e) => handleSettingsChange({ weekly_full_hour_local: parseInt(e.target.value) })}
                  disabled={savingSettings || !settings.weekly_full_enabled}
                  className="bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-2 py-1 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                >
                  {Array.from({ length: 24 }).map((_, h) => (
                    <option key={h} value={h}>{h.toString().padStart(2, "0")}:00</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={settings.weekly_full_timezone}
                  onChange={(e) => handleSettingsChange({ weekly_full_timezone: e.target.value })}
                  onBlur={(e) => handleSettingsChange({ weekly_full_timezone: e.target.value })}
                  disabled={savingSettings || !settings.weekly_full_enabled}
                  placeholder="America/Chicago"
                  className="w-40 bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-2 py-1 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                />
              </div>

              {settings.updated_at && (
                <p className="text-[10px] text-zinc-500">Last updated: {formatTimestamp(settings.updated_at)}</p>
              )}
            </div>
          </div>
        )}

        {/* History table */}
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900/20 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800/40">
            <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Sync History</h2>
            <span className="text-xs text-zinc-500">{history.length} runs</span>
          </div>
          {history.length === 0 ? (
            <p className="p-4 text-sm text-zinc-500">No syncs yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-50 dark:bg-zinc-900/50 text-left">
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Type</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Trigger</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Status</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Started</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-right">Duration</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-right">Contacts</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-right">Opportunities</th>
                  <th className="px-3 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-right">Errors</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr
                    key={r.id}
                    className={`border-t border-zinc-200 dark:border-zinc-800/20 ${r.errors_count > 0 ? "cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/30" : ""}`}
                    onClick={r.errors_count > 0 ? () => toggleErrorExpand(r.id) : undefined}
                  >
                    <td className="px-3 py-2 text-zinc-800 dark:text-zinc-300">{r.sync_type}</td>
                    <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">{r.trigger}</td>
                    <td className="px-3 py-2"><StatusPill status={r.status} /></td>
                    <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">{formatTimestamp(r.started_at)}</td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-800 dark:text-zinc-300">{formatDuration(r.duration_seconds)}</td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-800 dark:text-zinc-300">{r.contacts_synced.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-800 dark:text-zinc-300">{r.opportunities_synced.toLocaleString()}</td>
                    <td className={`px-3 py-2 text-right font-mono ${r.errors_count > 0 ? "text-red-400" : "text-zinc-500"}`}>{r.errors_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* Error details expandable */}
          {[...expandedErrors].map((runId) => {
            const run = history.find((h) => h.id === runId);
            if (!run || !run.error_details) return null;
            return (
              <div key={runId} className="px-4 py-3 bg-red-500/5 border-t border-red-500/20 text-[11px]">
                <div className="text-red-400 font-semibold mb-1">Errors for run {runId.slice(0, 8)}...</div>
                <pre className="text-zinc-600 dark:text-zinc-400 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(run.error_details, null, 2)}
                </pre>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
