"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchAssignmentContacts,
  markContactsUsed,
  type ApiContact,
  type AssignmentContactsResponse,
} from "@/lib/api";

/* ─── Types ───────────────────────────────────────────────────────────────── */

type StatusFilter = "assigned" | "used" | "all";

/* ─── Main Component ──────────────────────────────────────────────────────── */

export function ContactsPage({ assignmentId }: { assignmentId: string }) {
  const [data, setData] = useState<AssignmentContactsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<StatusFilter>("assigned");
  const [selectCount, setSelectCount] = useState<number>(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [marking, setMarking] = useState(false);

  /* ── Fetch contacts ─────────────────────────────────────────────────── */

  const load = useCallback(async (status: StatusFilter) => {
    try {
      const result = await fetchAssignmentContacts(assignmentId, status);
      setData(result);
    } catch (err) {
      console.error("Failed to load contacts:", err);
    } finally {
      setLoading(false);
    }
  }, [assignmentId]);

  useEffect(() => {
    setLoading(true);
    setSelectedIds(new Set());
    setSelectCount(0);
    load(filter);
  }, [filter, load]);

  /* ── Select N contacts ──────────────────────────────────────────────── */

  const applySelectCount = useCallback((n: number) => {
    if (!data) return;
    const ids = new Set<string>();
    const available = data.contacts.filter((c) => c.outreach_status === "assigned");
    const pool = filter === "assigned" ? available : data.contacts;
    for (let i = 0; i < Math.min(n, pool.length); i++) {
      ids.add(pool[i].id);
    }
    setSelectedIds(ids);
  }, [data, filter]);

  /* ── Copy emails to clipboard ───────────────────────────────────────── */

  const copyToClipboard = useCallback(async () => {
    if (!data || selectedIds.size === 0) return;
    setCopying(true);
    const emails = data.contacts
      .filter((c) => selectedIds.has(c.id))
      .map((c) => c.email)
      .join("\n");
    try {
      await navigator.clipboard.writeText(emails);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = emails;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } finally {
      setCopying(false);
    }
  }, [data, selectedIds]);

  /* ── Mark selected as used ──────────────────────────────────────────── */

  const handleMarkUsed = useCallback(async () => {
    if (selectedIds.size === 0) return;
    setMarking(true);
    try {
      await markContactsUsed(assignmentId, Array.from(selectedIds));
      // Reload to get fresh counts and filter out used ones
      setSelectedIds(new Set());
      setSelectCount(0);
      await load(filter);
    } catch (err) {
      console.error("Failed to mark contacts:", err);
    } finally {
      setMarking(false);
    }
  }, [assignmentId, selectedIds, filter, load]);

  /* ── Export all contacts as CSV ──────────────────────────────────────── */

  const exportCsv = useCallback(() => {
    if (!data || data.contacts.length === 0) return;
    const rows = [["email", "first_name", "status"]];
    for (const c of data.contacts) {
      rows.push([c.email, c.first_name || "", c.outreach_status]);
    }
    const csv = rows.map((r) => r.map((v) => `"${v.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const safeName = (data.assignment.list_name || data.assignment.bucket_name || "contacts").replace(/[^a-zA-Z0-9_-]/g, "_");
    a.download = `${safeName}_${filter}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [data, filter]);

  /* ── Toggle single row ──────────────────────────────────────────────── */

  const toggleContact = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /* ── Render ─────────────────────────────────────────────────────────── */

  if (loading && !data) {
    return (
      <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0 flex items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          Loading contacts...
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0 flex items-center justify-center">
        <p className="text-zinc-500">Assignment not found</p>
      </main>
    );
  }

  const { assignment, contacts, counts } = data;
  const listName = assignment.list_name
    || (assignment.bucket_name
      ? `W${assignment.webinar_number} — ${assignment.bucket_name}`
      : `Assignment`);

  const hasAssignedSelected = contacts.some(
    (c) => selectedIds.has(c.id) && c.outreach_status === "assigned"
  );

  return (
    <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0">
      <div className="px-6 py-5 max-w-[1000px] mx-auto">

        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="mb-5">
          <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">
            {listName}
          </h1>
          <div className="flex items-center gap-2 mt-1 text-sm text-zinc-500">
            {assignment.webinar_date && (
              <span>{new Date(assignment.webinar_date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
            )}
            <span className="text-zinc-300 dark:text-zinc-600">·</span>
            <span>{assignment.volume.toLocaleString()} total contacts</span>
          </div>
        </div>

        {/* ── Status Filter ─────────────────────────────────────────── */}
        <div className="flex items-center gap-2 mb-4">
          {(["assigned", "used", "all"] as StatusFilter[]).map((s) => {
            const label = s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1);
            const count = s === "assigned" ? counts.assigned : s === "used" ? counts.used : counts.total;
            const isActive = filter === s;
            return (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  isActive
                    ? s === "assigned"
                      ? "bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 border border-violet-200 dark:border-violet-500/25"
                      : s === "used"
                        ? "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/25"
                        : "bg-zinc-200 dark:bg-zinc-700 text-zinc-800 dark:text-zinc-200 border border-zinc-300 dark:border-zinc-600"
                    : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 border border-transparent"
                }`}
              >
                {label} ({count})
              </button>
            );
          })}
        </div>

        {/* ── Action Bar ────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 mb-4 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-xl px-4 py-3 shadow-sm">
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Select</label>
            <input
              type="number"
              min={0}
              max={contacts.length}
              value={selectCount}
              onChange={(e) => {
                const v = Math.max(0, Math.min(contacts.length, parseInt(e.target.value) || 0));
                setSelectCount(v);
                applySelectCount(v);
              }}
              className="w-20 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
            <span className="text-xs text-zinc-400">of {contacts.length}</span>
          </div>

          <div className="w-px h-5 bg-zinc-200 dark:bg-zinc-700" />

          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
            {selectedIds.size} selected
          </span>

          <div className="flex-1" />

          <button
            onClick={exportCsv}
            disabled={contacts.length === 0}
            className="px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Export CSV
          </button>

          <button
            onClick={copyToClipboard}
            disabled={selectedIds.size === 0 || copying}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              copied
                ? "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/25"
                : "bg-zinc-900 dark:bg-zinc-100 hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 disabled:opacity-40 disabled:cursor-not-allowed"
            }`}
          >
            {copied ? "Copied!" : "Copy Emails"}
          </button>

          {hasAssignedSelected && (
            <button
              onClick={handleMarkUsed}
              disabled={marking}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-wait text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              {marking && (
                <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              )}
              Mark as Used
            </button>
          )}
        </div>

        {/* ── Table ─────────────────────────────────────────────────── */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-zinc-50 dark:bg-zinc-800/30 border-b border-zinc-200 dark:border-zinc-800/40">
                <th className="w-10 px-3 py-2.5">
                  <input
                    type="checkbox"
                    checked={selectedIds.size > 0 && selectedIds.size === contacts.length}
                    onChange={() => {
                      if (selectedIds.size === contacts.length) {
                        setSelectedIds(new Set());
                        setSelectCount(0);
                      } else {
                        setSelectedIds(new Set(contacts.map((c) => c.id)));
                        setSelectCount(contacts.length);
                      }
                    }}
                    className="w-3.5 h-3.5 rounded border-zinc-300 dark:border-zinc-600 text-violet-600 focus:ring-violet-500 cursor-pointer accent-violet-600"
                  />
                </th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Email</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[180px]">First Name</th>
                {filter !== "assigned" && (
                  <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[120px]">Status</th>
                )}
              </tr>
            </thead>
            <tbody>
              {contacts.length === 0 ? (
                <tr>
                  <td colSpan={filter !== "assigned" ? 4 : 3} className="px-3 py-12 text-center text-zinc-400 text-sm">
                    No {filter === "all" ? "" : filter} contacts found
                  </td>
                </tr>
              ) : (
                contacts.map((c) => {
                  const isSelected = selectedIds.has(c.id);
                  return (
                    <tr
                      key={c.id}
                      onClick={() => toggleContact(c.id)}
                      className={`border-b border-zinc-100 dark:border-zinc-800/30 transition-colors cursor-pointer ${
                        isSelected ? "bg-violet-50/50 dark:bg-violet-500/5" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/20"
                      }`}
                    >
                      <td className="px-3 py-2.5">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleContact(c.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-3.5 h-3.5 rounded border-zinc-300 dark:border-zinc-600 text-violet-600 focus:ring-violet-500 cursor-pointer accent-violet-600"
                        />
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-zinc-800 dark:text-zinc-200">
                        {c.email}
                      </td>
                      <td className="px-3 py-2.5 text-zinc-600 dark:text-zinc-400 text-xs">
                        {c.first_name || "—"}
                      </td>
                      {filter !== "assigned" && (
                        <td className="px-3 py-2.5">
                          {c.outreach_status === "used" ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20">
                              Used
                              {c.used_at && (
                                <span className="font-normal normal-case ml-1 text-emerald-500/70">
                                  {new Date(c.used_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 border border-violet-200 dark:border-violet-500/20">
                              Assigned
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* ── Footer count ──────────────────────────────────────────── */}
        <div className="mt-3 text-xs text-zinc-400 text-right">
          Showing {contacts.length} contact{contacts.length !== 1 ? "s" : ""}
        </div>

      </div>
    </main>
  );
}
