"use client";

import { useState, useMemo, useEffect } from "react";
import {
  fetchStatisticsWebinars,
  fetchWgWebinars,
  syncWgSubscribers,
  type ApiStatisticsWebinar,
  type StatisticsMeta,
  type WgWebinar,
} from "@/lib/api";
import {
  METRIC_COLUMNS,
  METRIC_GROUPS,
  columnsInGroup,
  formatMetricValue,
  type MetricColumn,
} from "./metricRegistry";

/* ─── Identity columns (pinned left side of table) ────────────────────── */

const IDENTITY_COL_COUNT = 7; // expand, webinar#, status, note, description, url, sendInfo

/* ─── Status badge ────────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-zinc-500">\u2014</span>;
  const s = status.toLowerCase();
  const colors: Record<string, string> = {
    sent: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
    planning: "bg-amber-500/15 text-amber-500 border-amber-500/30",
    draft: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    cancelled: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${colors[s] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

/* ─── Metric cell ─────────────────────────────────────────────────────── */

function MetricCell({ value, col, bold }: { value: number | null | undefined; col: MetricColumn; bold?: boolean }) {
  const formatted = formatMetricValue(value, col);
  const isNull = value === null || value === undefined;
  return (
    <td className={`px-2 py-1.5 text-right font-mono whitespace-nowrap ${
      bold ? "font-bold" : ""
    } ${isNull ? "text-zinc-400" : bold ? "text-zinc-800 dark:text-zinc-200" : "text-zinc-700 dark:text-zinc-300"}`}>
      {formatted}
    </td>
  );
}

/* ─── External link icon ──────────────────────────────────────────────── */

function ExternalLinkIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

/* ─── Main Component ──────────────────────────────────────────────────── */

export function StatisticsPage() {
  const [webinars, setWebinars] = useState<ApiStatisticsWebinar[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState<StatisticsMeta | null>(null);

  /* ── WebinarGeek sync ──────────────────────────────────────────── */
  const [wgWebinars, setWgWebinars] = useState<WgWebinar[]>([]);
  const [wgSelected, setWgSelected] = useState<string>("");
  const [wgSyncing, setWgSyncing] = useState(false);
  const [wgMessage, setWgMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchWgWebinars()
      .then(({ webinars }) => setWgWebinars(webinars))
      .catch(() => { /* connector not configured — silently skip */ });
  }, []);

  async function handleWgSync() {
    if (!wgSelected) return;
    setWgSyncing(true);
    setWgMessage(null);
    try {
      const res = await syncWgSubscribers(wgSelected);
      setWgMessage(`Synced ${res.total} subscribers.`);
      const { webinars } = await fetchWgWebinars();
      setWgWebinars(webinars);
    } catch (e) {
      setWgMessage(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setWgSyncing(false);
    }
  }

  /* ── Load data ──────────────────────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { webinars: data, meta } = await fetchStatisticsWebinars();
        if (cancelled) return;
        setMeta(meta);
        // Sort descending by webinar number
        data.sort((a, b) => b.number - a.number);
        setWebinars(data);
        // Expand the latest webinar by default
        if (data.length > 0) {
          setExpandedIds(new Set([data[0].number]));
        }
      } catch (err) {
        console.error("Failed to load statistics:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  /* ── Search filter ──────────────────────────────────────────────── */
  const filteredWebinars = useMemo(() => {
    if (!searchQuery.trim()) return webinars;
    const q = searchQuery.toLowerCase();
    return webinars.filter((w) => {
      if (String(w.number).includes(q)) return true;
      if (w.title?.toLowerCase().includes(q)) return true;
      if (w.date?.toLowerCase().includes(q)) return true;
      return w.rows.some(
        (r) =>
          r.description?.toLowerCase().includes(q) ||
          r.note?.toLowerCase().includes(q) ||
          r.sendInfo?.toLowerCase().includes(q)
      );
    });
  }, [webinars, searchQuery]);

  /* ── Global summary stats ───────────────────────────────────────── */
  const globalStats = useMemo(() => {
    const totalInvited = webinars.reduce((s, w) => s + (w.summary.invited ?? 0), 0);
    const totalAttended = webinars.reduce((s, w) => s + (w.summary.totalAttended ?? 0), 0);
    const totalBookings = webinars.reduce((s, w) => s + (w.summary.totalBookings ?? 0), 0);
    const totalWon = webinars.reduce((s, w) => s + (w.summary.won ?? 0), 0);
    return { totalInvited, totalAttended, totalBookings, totalWon };
  }, [webinars]);

  /* ── Toggle expand ──────────────────────────────────────────────── */
  const toggleExpand = (num: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  /* ── Loading state ──────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-zinc-500">Loading statistics...</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* ── Sticky header ──────────────────────────────────────────── */}
      <div className="sticky top-12 z-40 bg-white dark:bg-zinc-950/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800/40 px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Statistics</h1>
            {meta && (
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                  meta.source === "ghl"
                    ? "bg-violet-500/15 text-violet-400 border-violet-500/30"
                    : "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"
                }`}
                title={
                  meta.source === "ghl" && meta.last_sync?.completed_at
                    ? `Last synced: ${new Date(meta.last_sync.completed_at).toLocaleString()}`
                    : meta.source === "ghl"
                    ? "GHL sync running"
                    : "Using workbook fixture (no GHL sync yet)"
                }
              >
                {meta.source === "ghl"
                  ? `GHL · synced ${meta.last_sync?.completed_at ? new Date(meta.last_sync.completed_at).toLocaleDateString() : "—"}`
                  : "Workbook"}
              </span>
            )}
            <div className="flex gap-2">
              {[
                { label: "Webinars", value: webinars.length, color: "text-zinc-800 dark:text-zinc-200" },
                { label: "Invited", value: globalStats.totalInvited.toLocaleString(), color: "text-violet-400" },
                { label: "Attended", value: globalStats.totalAttended.toLocaleString(), color: "text-emerald-400" },
                { label: "Bookings", value: globalStats.totalBookings, color: "text-amber-400" },
                { label: "Won", value: globalStats.totalWon, color: "text-sky-400" },
              ].map((s) => (
                <div key={s.label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/40">
                  <span className={`text-sm font-bold font-mono ${s.color}`}>{s.value}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {wgWebinars.length > 0 && (
              <div className="flex items-center gap-2">
                <select
                  value={wgSelected}
                  onChange={(e) => { setWgSelected(e.target.value); setWgMessage(null); }}
                  className="bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 max-w-[260px]"
                >
                  <option value="">WebinarGeek: select broadcast…</option>
                  {wgWebinars.map((w) => (
                    <option key={w.broadcast_id} value={w.broadcast_id}>
                      {w.name} — {w.broadcast_id}
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleWgSync}
                  disabled={!wgSelected || wgSyncing}
                  className="px-3 py-1.5 text-xs rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {wgSyncing ? "Syncing..." : "Sync"}
                </button>
                {wgMessage && (
                  <span className="text-[10px] text-zinc-500 max-w-[180px] truncate" title={wgMessage}>
                    {wgMessage}
                  </span>
                )}
              </div>
            )}
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search webinars..."
              className="w-56 bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
        </div>
      </div>

      {/* ── Table ──────────────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[3200px]">
          <thead>
            {/* Row 1: Group spans */}
            <tr className="bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-100 dark:border-zinc-800/20">
              <th colSpan={IDENTITY_COL_COUNT} className="px-2 py-1"></th>
              {METRIC_GROUPS.map((g) => (
                <th
                  key={g}
                  colSpan={columnsInGroup(g)}
                  className="text-center px-1 py-1 text-[9px] font-bold uppercase tracking-wider text-zinc-400 border-l border-zinc-200 dark:border-zinc-800/30"
                >
                  {g}
                </th>
              ))}
            </tr>
            {/* Row 2: Individual column labels */}
            <tr className="bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-200 dark:border-zinc-800/40">
              <th className="w-8 px-2 py-2"></th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[140px]">Webinar #</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Status</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[120px]">Note</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[200px]">Description</th>
              <th className="text-center px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] w-8">URL</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[80px]">Send Info</th>
              {METRIC_COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] whitespace-nowrap"
                  title={col.formulaText}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>

          {filteredWebinars.map((w) => {
            const isExpanded = expandedIds.has(w.number);
            const listCount = w.rows.filter((r) => r.kind === "list").length;

            return (
              <tbody key={w.id}>
                {/* ── Parent row ─────────────────────────────────── */}
                <tr
                  className="bg-zinc-100 dark:bg-zinc-800/40 hover:bg-zinc-200 dark:hover:bg-zinc-800/60 cursor-pointer border-t-2 border-zinc-300 dark:border-zinc-700/40 transition-colors"
                  onClick={() => toggleExpand(w.number)}
                >
                  <td className="px-2 py-2.5 text-center">
                    <svg
                      width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                      className={`text-zinc-600 dark:text-zinc-400 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                    >
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </td>
                  <td className="px-2 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-900 dark:text-zinc-100 font-bold text-sm">{w.number}</span>
                      <span className="text-zinc-500">{w.date ?? "\u2014"}</span>
                    </div>
                    {w.title && w.title !== "TOTAL" && (
                      <div className="text-[10px] text-zinc-500 mt-0.5 truncate max-w-[200px]">{w.title}</div>
                    )}
                  </td>
                  <td className="px-2 py-2.5">
                    <StatusBadge status={w.rows[0]?.status ?? null} />
                  </td>
                  <td className="px-2 py-2.5 text-zinc-500 text-[10px]">
                    {listCount} lists
                  </td>
                  <td className="px-2 py-2.5" colSpan={3}></td>
                  {METRIC_COLUMNS.map((col) => (
                    <MetricCell key={col.key} value={w.summary[col.key]} col={col} bold />
                  ))}
                </tr>

                {/* ── Child rows ─────────────────────────────────── */}
                {isExpanded && w.rows.map((row) => (
                  <tr
                    key={row.id}
                    className={`border-b border-zinc-200 dark:border-zinc-800/20 transition-colors ${
                      row.kind !== "list"
                        ? "bg-zinc-50 dark:bg-zinc-900/20 text-zinc-500 italic"
                        : "hover:bg-zinc-100 dark:hover:bg-zinc-800/20"
                    }`}
                  >
                    <td className="px-2 py-1.5"></td>
                    <td className="px-2 py-1.5"></td>
                    <td className="px-2 py-1.5">
                      {row.kind === "list" && <StatusBadge status={row.status} />}
                    </td>
                    <td className="px-2 py-1.5">
                      <span className={row.kind !== "list" ? "text-zinc-500" : "text-zinc-700 dark:text-zinc-300"}>
                        {row.note ?? ""}
                      </span>
                    </td>
                    <td className="px-2 py-1.5">
                      <span className={row.kind !== "list" ? "text-zinc-500" : "text-zinc-800 dark:text-zinc-300"}>
                        {row.description ?? (row.kind === "nonjoiners" ? "Nonjoiners" : row.kind === "no_list_data" ? "NO LIST DATA" : "")}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {row.listUrl && (
                        <a
                          href={row.listUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          title={row.listUrl}
                          className="text-violet-400 hover:text-violet-300"
                        >
                          <ExternalLinkIcon />
                        </a>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-zinc-600 dark:text-zinc-400">
                      {row.sendInfo ?? ""}
                    </td>
                    {METRIC_COLUMNS.map((col) => (
                      <MetricCell key={col.key} value={row.metrics[col.key]} col={col} />
                    ))}
                  </tr>
                ))}
              </tbody>
            );
          })}
        </table>
      </div>

      {/* ── Empty state ────────────────────────────────────────────── */}
      {!loading && filteredWebinars.length === 0 && (
        <div className="text-center py-20 text-zinc-500">
          {searchQuery ? "No webinars match your search." : "No statistics data available."}
        </div>
      )}
    </div>
  );
}
