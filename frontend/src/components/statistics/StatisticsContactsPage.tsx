"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  fetchStatisticsContacts,
  type ContactDrilldownResponse,
} from "@/lib/api";
import { METRIC_COLUMNS } from "./metricRegistry";

function metricLabel(key: string): string {
  const col = METRIC_COLUMNS.find((c) => c.key === key);
  if (!col) return key;
  return `${col.group} · ${col.label}`;
}

function ExternalIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

export function StatisticsContactsPage() {
  const params = useSearchParams();
  const webinar = Number(params.get("webinar"));
  const metric = params.get("metric") ?? "";
  const assignment = params.get("assignment") ?? null;
  const listLabel = params.get("list") ?? null; // optional display label

  const [data, setData] = useState<ContactDrilldownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!webinar || !metric) {
      setLoading(false);
      setError("Missing required query params: webinar, metric");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchStatisticsContacts({ webinar, metric, assignment });
        if (cancelled) return;
        setData(res);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [webinar, metric, assignment]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-zinc-500">Loading contacts...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return <div className="px-6 py-12 text-sm text-red-400">{error}</div>;
  }

  if (!data) return null;

  return (
    <div>
      <div className="sticky top-12 z-40 bg-white dark:bg-zinc-950/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800/40 px-6 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">
            Webinar {data.webinar_number} · {metricLabel(data.metric)}
          </h1>
          <span className="text-xs text-zinc-500">
            {listLabel ? `list: ${listLabel} · ` : ""}{data.total} {data.unit === "opportunity" ? "opportunities" : "contacts"}
          </span>
        </div>
      </div>

      <div className="px-6 py-6 max-w-5xl">
        {!data.available && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-500 mb-4">
            {data.reason ?? "Drill-down unavailable for this metric."}
          </div>
        )}

        {data.items.length === 0 ? (
          <p className="text-sm text-zinc-500">No {data.unit === "opportunity" ? "opportunities" : "contacts"} found.</p>
        ) : (
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900/20 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-50 dark:bg-zinc-900/50 text-left border-b border-zinc-200 dark:border-zinc-800/40">
                  <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Name</th>
                  <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Email</th>
                  <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Company</th>
                  {data.unit === "opportunity" && (
                    <>
                      <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Call 1 Status</th>
                      <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Lead Quality</th>
                      <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-right">Value</th>
                    </>
                  )}
                  <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-center">GHL</th>
                  {data.unit === "opportunity" && (
                    <th className="px-4 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] text-center">Opp</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {data.items.map((it, i) => {
                  const fullName = [it.first_name, it.last_name].filter(Boolean).join(" ") || "—";
                  return (
                    <tr key={`${it.ghl_contact_id}-${it.opportunity_id ?? i}`} className="border-t border-zinc-200 dark:border-zinc-800/20">
                      <td className="px-4 py-2 text-zinc-800 dark:text-zinc-200">{fullName}</td>
                      <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400 font-mono">{it.email ?? "—"}</td>
                      <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{it.company_website ?? "—"}</td>
                      {data.unit === "opportunity" && (
                        <>
                          <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{it.call1_status ?? "—"}</td>
                          <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{it.lead_quality ?? "—"}</td>
                          <td className="px-4 py-2 text-right font-mono text-zinc-600 dark:text-zinc-400">
                            {it.opportunity_value != null ? `$${it.opportunity_value.toLocaleString()}` : "—"}
                          </td>
                        </>
                      )}
                      <td className="px-4 py-2 text-center">
                        <a
                          href={it.ghl_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-violet-500 hover:text-violet-400"
                          title="Open contact in GHL"
                        >
                          <ExternalIcon />
                        </a>
                      </td>
                      {data.unit === "opportunity" && (
                        <td className="px-4 py-2 text-center">
                          {it.opportunity_url ? (
                            <a
                              href={it.opportunity_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-sky-500 hover:text-sky-400"
                              title="Open opportunity in GHL"
                            >
                              <ExternalIcon />
                            </a>
                          ) : "—"}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
