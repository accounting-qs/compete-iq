"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addBlocklistEntry,
  bulkAddBlocklist,
  deleteBlocklistEntry,
  fetchBlocklist,
  type BlocklistEntry,
  type BlocklistSource,
} from "@/lib/api";

const SOURCE_LABELS: Record<BlocklistSource, string> = {
  ghl_dnd: "GHL DND",
  wg_unsub: "WebinarGeek unsub",
  manual: "Manual",
  csv: "CSV import",
};

const SOURCE_BADGE_CLS: Record<BlocklistSource, string> = {
  ghl_dnd: "bg-rose-100 dark:bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-500/25",
  wg_unsub: "bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/25",
  manual: "bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-200 dark:border-violet-500/25",
  csv: "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/25",
};

function parseEmailsFromCsv(text: string): string[] {
  const emails: string[] = [];
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    for (const cell of line.split(/[,;\t]/)) {
      const t = cell.trim().replace(/^"|"$/g, "");
      if (t.includes("@")) emails.push(t);
    }
  }
  return emails;
}

export function BlocklistPage() {
  const [entries, setEntries] = useState<BlocklistEntry[]>([]);
  const [bySource, setBySource] = useState<Partial<Record<BlocklistSource, number>>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [sourceFilter, setSourceFilter] = useState<BlocklistSource | "">("");

  const [addEmail, setAddEmail] = useState("");
  const [addReason, setAddReason] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchBlocklist({
        q: q || undefined,
        source: sourceFilter || undefined,
        limit: 1000,
      });
      setEntries(res.entries);
      setBySource(res.by_source);
      setTotal(res.total);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [q, sourceFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);
    const email = addEmail.trim();
    if (!email) return;
    setAdding(true);
    try {
      await addBlocklistEntry({ email, reason: addReason.trim() || undefined });
      setAddEmail("");
      setAddReason("");
      await load();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  }, [addEmail, addReason, load]);

  const handleImport = useCallback(async (file: File) => {
    setImporting(true);
    setImportResult(null);
    try {
      const text = await file.text();
      const emails = parseEmailsFromCsv(text);
      if (emails.length === 0) {
        setImportResult("No emails found in file.");
        return;
      }
      const res = await bulkAddBlocklist({ emails });
      setImportResult(
        `Imported ${res.added} new · ${res.skipped} already on list · ${res.invalid} invalid`
      );
      await load();
    } catch (err) {
      setImportResult(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [load]);

  const handleDelete = useCallback(async (id: string, email: string) => {
    if (!confirm(`Remove ${email} from the blocklist?`)) return;
    try {
      await deleteBlocklistEntry(id);
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove");
    }
  }, [load]);

  const sourceCounts: { key: BlocklistSource; label: string; count: number }[] = useMemo(
    () => (["ghl_dnd", "wg_unsub", "manual", "csv"] as BlocklistSource[]).map((k) => ({
      key: k,
      label: SOURCE_LABELS[k],
      count: bySource[k] ?? 0,
    })),
    [bySource],
  );

  return (
    <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0">
      <div className="px-6 py-5 max-w-[1100px] mx-auto">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="mb-5 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">
              Blocklist
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Emails excluded from outreach. Synced automatically from GHL DND and
              WebinarGeek unsubscribes; removed contacts are also skipped when
              assigning buckets and hidden on the list contacts tab.
            </p>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Total</div>
            <div className="text-2xl font-mono text-zinc-900 dark:text-zinc-100">{total.toLocaleString()}</div>
          </div>
        </div>

        {/* ── Source breakdown ──────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {sourceCounts.map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setSourceFilter(sourceFilter === key ? "" : key)}
              className={`rounded-xl border px-3 py-2.5 text-left transition-colors ${
                sourceFilter === key
                  ? "border-violet-400 dark:border-violet-500/50 bg-violet-50 dark:bg-violet-500/10"
                  : "border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-700"
              }`}
            >
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
              <div className="text-lg font-mono text-zinc-900 dark:text-zinc-100 mt-0.5">{count.toLocaleString()}</div>
            </button>
          ))}
        </div>

        {/* ── Add + Import bar ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
          <form
            onSubmit={handleAdd}
            className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-xl px-4 py-3 shadow-sm flex items-center gap-2"
          >
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Add</label>
            <input
              type="email"
              required
              placeholder="email@example.com"
              value={addEmail}
              onChange={(e) => setAddEmail(e.target.value)}
              className="flex-1 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
            <input
              type="text"
              placeholder="Reason (optional)"
              value={addReason}
              onChange={(e) => setAddReason(e.target.value)}
              className="w-40 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-2 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
            <button
              type="submit"
              disabled={adding || !addEmail.trim()}
              className="px-3 py-1.5 bg-zinc-900 dark:bg-zinc-100 hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-semibold rounded-md disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {adding ? "Adding…" : "Add"}
            </button>
          </form>

          <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-xl px-4 py-3 shadow-sm flex items-center gap-2">
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">CSV Import</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              disabled={importing}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleImport(f);
              }}
              className="flex-1 text-xs text-zinc-600 dark:text-zinc-400 file:mr-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-zinc-100 file:dark:bg-zinc-800 file:text-zinc-700 file:dark:text-zinc-300 hover:file:bg-zinc-200 dark:hover:file:bg-zinc-700"
            />
            {importResult && (
              <span className="text-[11px] text-zinc-500 truncate max-w-[240px]" title={importResult}>
                {importResult}
              </span>
            )}
          </div>
        </div>

        {addError && (
          <div className="mb-3 text-xs text-rose-500 bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-md px-3 py-2">
            {addError}
          </div>
        )}

        {/* ── Search + Filter ───────────────────────────────────────── */}
        <div className="flex items-center gap-2 mb-3">
          <input
            type="text"
            placeholder="Search email…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="flex-1 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-md px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
          />
          {sourceFilter && (
            <button
              onClick={() => setSourceFilter("")}
              className="px-2 py-1 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              Clear filter ({SOURCE_LABELS[sourceFilter]}) ×
            </button>
          )}
        </div>

        {/* ── Table ─────────────────────────────────────────────────── */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-zinc-50 dark:bg-zinc-800/30 border-b border-zinc-200 dark:border-zinc-800/40">
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Email</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[140px]">Source</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Reason</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[120px]">Added</th>
                <th className="w-[80px]"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-3 py-12 text-center text-zinc-400 text-sm">
                    Loading…
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-12 text-center text-zinc-400 text-sm">
                    {q || sourceFilter ? "No matching entries" : "Blocklist is empty"}
                  </td>
                </tr>
              ) : entries.map((e) => (
                <tr key={e.id} className="border-b border-zinc-100 dark:border-zinc-800/30 hover:bg-zinc-50 dark:hover:bg-zinc-800/20">
                  <td className="px-3 py-2 font-mono text-xs text-zinc-800 dark:text-zinc-200">{e.email}</td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${SOURCE_BADGE_CLS[e.source] ?? SOURCE_BADGE_CLS.manual}`}>
                      {SOURCE_LABELS[e.source] ?? e.source}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-600 dark:text-zinc-400">{e.reason || "—"}</td>
                  <td className="px-3 py-2 text-xs text-zinc-500">
                    {e.created_at ? new Date(e.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleDelete(e.id, e.email)}
                      className="px-2 py-1 text-[11px] text-zinc-500 hover:text-rose-500 rounded transition-colors"
                      title="Remove from blocklist"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-3 text-xs text-zinc-400 text-right">
          Showing {entries.length} of {total.toLocaleString()}
        </div>

      </div>
    </main>
  );
}
