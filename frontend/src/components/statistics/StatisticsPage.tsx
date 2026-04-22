"use client";

import { useState, useMemo, useEffect, type ReactNode } from "react";
import {
  fetchStatisticsWebinars,
  fetchWgWebinars,
  syncWgSubscribers,
  triggerGhlWebinarSync,
  type ApiStatisticsRow,
  type ApiStatisticsWebinar,
  type StatisticsMeta,
  type WgWebinar,
} from "@/lib/api";
import {
  GROUP_BOUNDARY_CLASSES,
  METRIC_COLUMNS,
  METRIC_GROUPS,
  columnsInGroup,
  formatMetricValue,
  isGroupBoundary,
  type MetricColumn,
} from "./metricRegistry";

/* ─── Identity columns (pinned left side of table) ────────────────────── */

const IDENTITY_COL_COUNT = 8; // expand, webinar#, status, note, description, copy, url, sendInfo

/* ─── Sticky identity columns ─────────────────────────────────────────────
 * Description, Copy, URL, and Send Info stay visible while the wide metric
 * band scrolls horizontally. Each column is a fixed width; left offsets
 * are cumulative so they line up as a single frozen panel:
 *   Description: 240px wide  @ left-0
 *   Copy:        260px wide  @ left-[240px]
 *   URL:          32px wide  @ left-[500px]
 *   Send Info:   120px wide  @ left-[532px]
 *   (total sticky pane: 652px)
 * Each row type gets its own background so scrolling content doesn't
 * bleed through the sticky cells. */

// z-index: header stacks above rows; list/parent/group stack above metrics
const Z_HEADER = "z-30";
const Z_ROW = "z-20";

// Vertical sticky offsets for the two thead rows so the table header stays
// fixed under the page's sticky top-12 header when the user scrolls down.
// Page header (nav 48px + Statistics bar ~60px) ends near 108px; then the
// band-label row (~24px tall) sits above the column-label row.
const TOP_BAND_ROW = "top-[108px]";
const TOP_LABEL_ROW = "top-[132px]";

// Row-type backgrounds (must be opaque so scroll doesn't bleed through)
const BG_HEADER = "bg-zinc-50 dark:bg-zinc-900";
const BG_PARENT = "bg-zinc-100 dark:bg-zinc-800";
const BG_GROUP = "bg-zinc-100 dark:bg-zinc-800";
const BG_LIST = "bg-white dark:bg-zinc-950";
const BG_SPECIAL = "bg-zinc-50 dark:bg-zinc-900";

// Sticky left offsets — full class strings so Tailwind can pick them up
const L_DESC = "sticky left-0";
const L_COPY = "sticky left-[240px]";
const L_URL = "sticky left-[500px]";
const L_SEND = "sticky left-[532px]";

// Fixed widths — use w-[] to lock each sticky column
const W_DESC = "w-[240px] min-w-[240px] max-w-[240px]";
const W_COPY = "w-[260px] min-w-[260px] max-w-[260px]";
const W_URL = "w-[32px] min-w-[32px] max-w-[32px]";
const W_SEND = "w-[120px] min-w-[120px] max-w-[120px]";

// Composite classes (left + z + bg) per row type / column.
// Header cells also get the vertical-sticky TOP_LABEL_ROW so they stay
// pinned while the body scrolls vertically.
const sDescH = `${L_DESC} ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`;
const sCopyH = `${L_COPY} ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`;
const sUrlH = `${L_URL} ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`;
const sSendH = `${L_SEND} ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`;

const sDescP = `${L_DESC} ${Z_ROW} ${BG_PARENT}`;
// (parent-row's colSpan={4} cell spans Desc+Copy+URL+Send, one sticky cell)

const sDescG = `${L_DESC} ${Z_ROW} ${BG_GROUP}`;
const sCopyG = `${L_COPY} ${Z_ROW} ${BG_GROUP}`;
const sUrlG = `${L_URL} ${Z_ROW} ${BG_GROUP}`;
const sSendG = `${L_SEND} ${Z_ROW} ${BG_GROUP}`;

const sDescL = `${L_DESC} ${Z_ROW} ${BG_LIST}`;
const sCopyL = `${L_COPY} ${Z_ROW} ${BG_LIST}`;
const sUrlL = `${L_URL} ${Z_ROW} ${BG_LIST}`;
const sSendL = `${L_SEND} ${Z_ROW} ${BG_LIST}`;

const sDescSp = `${L_DESC} ${Z_ROW} ${BG_SPECIAL}`;
const sCopySp = `${L_COPY} ${Z_ROW} ${BG_SPECIAL}`;
const sUrlSp = `${L_URL} ${Z_ROW} ${BG_SPECIAL}`;
const sSendSp = `${L_SEND} ${Z_ROW} ${BG_SPECIAL}`;

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

/** Keys that can be drilled down to a contact list. */
const DRILLDOWN_KEYS = new Set([
  "gcalInvitedGhl",
  "unsubscribes",
  "lpRegs",
  "yesMarked", "yesAttended", "yes10MinPlus", "yesAttendBySmsClick", "yesBookings",
  "maybeMarked", "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick", "maybeBookings",
  "selfRegMarked", "selfRegAttended", "selfReg10MinPlus", "selfRegBookings",
  "totalRegs", "totalAttended", "total10MinPlus", "total30MinPlus", "attendBySmsReminder",
  "totalBookings", "totalCallsDatePassed", "confirmed", "shows", "noShows",
  "canceled", "won", "disqualified", "qualified",
  "leadQualityGreat", "leadQualityOk", "leadQualityBarelyPassable", "leadQualityBadDq",
]);

function MetricCell({
  value, col, bold, boundary, webinarNumber, assignmentId, listLabel,
}: {
  value: number | null | undefined;
  col: MetricColumn;
  bold?: boolean;
  boundary?: boolean;
  webinarNumber?: number;
  assignmentId?: string | null;
  listLabel?: string | null;
}) {
  const formatted = formatMetricValue(value, col);
  const isNull = value === null || value === undefined;
  const isNonZero = typeof value === "number" && value > 0;
  const drillable = webinarNumber != null && DRILLDOWN_KEYS.has(col.key) && isNonZero;

  const content = drillable ? (
    <a
      href={(() => {
        const qs = new URLSearchParams({
          webinar: String(webinarNumber),
          metric: col.key,
        });
        if (assignmentId) qs.set("assignment", assignmentId);
        if (listLabel) qs.set("list", listLabel);
        return `/statistics/contacts?${qs.toString()}`;
      })()}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="hover:text-violet-500 dark:hover:text-violet-400 underline underline-offset-2 decoration-dotted decoration-zinc-400/40"
      title={`Click to see the ${col.group} · ${col.label} contacts`}
    >
      {formatted}
    </a>
  ) : (
    formatted
  );

  return (
    <td className={`px-2 py-1.5 text-right font-mono whitespace-nowrap ${
      bold ? "font-bold" : ""
    } ${isNull ? "text-zinc-400" : bold ? "text-zinc-800 dark:text-zinc-200" : "text-zinc-700 dark:text-zinc-300"} ${
      boundary ? GROUP_BOUNDARY_CLASSES : ""
    }`}>
      {content}
    </td>
  );
}

/* ─── External link icon ──────────────────────────────────────────────── */

/* ─── Copy (title + description) preview + modal ─────────────────────── */

function VariantBadge({ idx, kind }: { idx: number; kind: "title" | "desc" }) {
  const colors = kind === "title"
    ? "bg-violet-500/15 text-violet-500 border-violet-500/30"
    : "bg-sky-500/15 text-sky-500 border-sky-500/30";
  return (
    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${colors}`}>
      V{idx + 1}
    </span>
  );
}

function CopyCell({ row, onClick }: { row: ApiStatisticsRow; onClick: () => void }) {
  const t = row.titleCopy;
  const d = row.descCopy;
  if (!t && !d) return <span className="text-zinc-600">—</span>;
  return (
    <div
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="cursor-pointer group/copy max-w-[260px]"
      title="Click to view full title + description"
    >
      {t && (
        <div className="flex items-center gap-1 mb-0.5">
          <VariantBadge idx={t.variantIndex} kind="title" />
          <span className="text-[10px] text-zinc-700 dark:text-zinc-300 truncate group-hover/copy:text-violet-500 dark:group-hover/copy:text-violet-400">
            {t.text}
          </span>
        </div>
      )}
      {d && (
        <div className="flex items-center gap-1">
          <VariantBadge idx={d.variantIndex} kind="desc" />
          <span className="text-[10px] text-zinc-600 dark:text-zinc-400 truncate group-hover/copy:text-sky-500 dark:group-hover/copy:text-sky-400">
            {d.text.split("\n")[0]}
          </span>
        </div>
      )}
    </div>
  );
}

function CopyModal({ row, onClose }: { row: ApiStatisticsRow; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl shadow-2xl max-w-2xl w-[90vw] max-h-[80vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-0.5">Copy used for list</div>
            <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
              {row.description ?? row.listName ?? "—"}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors"
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div className="px-6 py-4 space-y-4">
          <section>
            <div className="flex items-center gap-2 mb-2">
              <VariantBadge idx={row.titleCopy?.variantIndex ?? 0} kind="title" />
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Title</span>
            </div>
            {row.titleCopy ? (
              <p className="text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">{row.titleCopy.text}</p>
            ) : (
              <p className="text-sm text-zinc-500 italic">No title copy set</p>
            )}
          </section>
          <section>
            <div className="flex items-center gap-2 mb-2">
              <VariantBadge idx={row.descCopy?.variantIndex ?? 0} kind="desc" />
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Description</span>
            </div>
            {row.descCopy ? (
              <p className="text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">{row.descCopy.text}</p>
            ) : (
              <p className="text-sm text-zinc-500 italic">No description copy set</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

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

/* ─── Bucket-grouped child-row renderer ─────────────────────────────── */

const BASE_SUM_KEYS = ["listSize", "listRemain", "gcalInvited", "accountsNeeded", "invited"] as const;

function sumMetric(rows: ApiStatisticsRow[], key: string): number {
  let total = 0;
  for (const r of rows) {
    const v = r.metrics[key];
    if (typeof v === "number") total += v;
  }
  return total;
}

/**
 * Render child rows for an expanded webinar, grouped by bucket like the
 * Planning page: multi-list buckets collapse under a header row, single-list
 * buckets go into a synthetic "Unique Buckets" group, and Nonjoiners /
 * NO LIST DATA rows render below as-is.
 */
function renderGroupedRows(
  w: ApiStatisticsWebinar,
  collapsedBuckets: Set<string>,
  toggleBucketGroup: (webinarId: string, groupKey: string) => void,
  setCopyModalRow: (row: ApiStatisticsRow) => void,
): ReactNode[] {
  type Group = { bucketId: string; bucketName: string; lists: ApiStatisticsRow[] };

  const groups: Group[] = [];
  const seen = new Map<string, number>();
  const unbucketed: ApiStatisticsRow[] = [];
  const specials: ApiStatisticsRow[] = [];

  for (const r of w.rows) {
    if (r.kind !== "list") { specials.push(r); continue; }
    if (!r.bucketId) { unbucketed.push(r); continue; }
    const idx = seen.get(r.bucketId);
    if (idx !== undefined) {
      groups[idx].lists.push(r);
    } else {
      seen.set(r.bucketId, groups.length);
      groups.push({
        bucketId: r.bucketId,
        bucketName: r.bucketName ?? r.description ?? "Bucket",
        lists: [r],
      });
    }
  }

  const multi = groups.filter((g) => g.lists.length >= 2);
  const single = groups.filter((g) => g.lists.length === 1).map((g) => g.lists[0]);

  const renderListRow = (row: ApiStatisticsRow) => {
    const isSpecial = row.kind !== "list";
    const desc = isSpecial ? sDescSp : sDescL;
    const copy = isSpecial ? sCopySp : sCopyL;
    const url = isSpecial ? sUrlSp : sUrlL;
    const send = isSpecial ? sSendSp : sSendL;
    return (
    <tr
      key={row.id}
      className={`border-b border-zinc-200 dark:border-zinc-800/20 transition-colors ${
        isSpecial
          ? "bg-zinc-50 dark:bg-zinc-900/20 text-zinc-500 italic"
          : "hover:bg-zinc-100 dark:hover:bg-zinc-800/20"
      }`}
    >
      <td className="px-2 py-1.5"></td>
      <td className="px-2 py-1.5"></td>
      <td className="px-2 py-1.5">
        {!isSpecial && <StatusBadge status={row.status} />}
      </td>
      <td className="px-2 py-1.5">
        <span className={isSpecial ? "text-zinc-500" : "text-zinc-700 dark:text-zinc-300"}>
          {row.note ?? ""}
        </span>
      </td>
      <td className={`px-2 py-1.5 ${W_DESC} ${desc}`}>
        <span className={`block truncate ${isSpecial ? "text-zinc-500" : "text-zinc-800 dark:text-zinc-300"}`} title={row.description ?? undefined}>
          {row.description ?? (row.kind === "nonjoiners" ? "Nonjoiners" : row.kind === "no_list_data" ? "NO LIST DATA" : "")}
        </span>
      </td>
      <td className={`px-2 py-1.5 ${W_COPY} ${copy}`}>
        <CopyCell row={row} onClick={() => setCopyModalRow(row)} />
      </td>
      <td className={`px-2 py-1.5 text-center ${W_URL} ${url}`}>
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
      <td className={`px-2 py-1.5 text-zinc-600 dark:text-zinc-400 ${W_SEND} ${send}`}>
        <span className="block truncate" title={row.sendInfo ?? undefined}>
          {row.sendInfo ?? ""}
        </span>
      </td>
      {METRIC_COLUMNS.map((col, idx) => (
        <MetricCell
          key={col.key}
          value={row.metrics[col.key]}
          col={col}
          boundary={isGroupBoundary(idx)}
          webinarNumber={w.number}
          assignmentId={row.assignmentId}
          listLabel={row.description}
        />
      ))}
    </tr>
    );
  };

  const renderGroupHeader = (groupKey: string, bucketName: string, lists: ApiStatisticsRow[], italic = false) => {
    const key = `${w.id}::${groupKey}`;
    const collapsed = collapsedBuckets.has(key);
    const uniqSenders: { name: string; color: string | null }[] = [];
    const seenSenders = new Set<string>();
    for (const l of lists) {
      if (l.sendInfo && !seenSenders.has(l.sendInfo)) {
        seenSenders.add(l.sendInfo);
        uniqSenders.push({ name: l.sendInfo, color: l.senderColor });
      }
    }
    const summed: Record<string, number> = {};
    for (const k of BASE_SUM_KEYS) summed[k] = sumMetric(lists, k);

    return (
      <tr
        key={`bucket-${groupKey}`}
        onClick={() => toggleBucketGroup(w.id, groupKey)}
        className="bg-zinc-100/70 dark:bg-zinc-800/25 hover:bg-zinc-200/70 dark:hover:bg-zinc-800/45 cursor-pointer border-b border-zinc-200 dark:border-zinc-800/30 transition-colors"
      >
        <td className="px-2 py-2 text-center">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            className={`text-zinc-500 dark:text-zinc-400 transition-transform duration-200 ${collapsed ? "" : "rotate-90"}`}>
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </td>
        <td className="px-2 py-2"></td>
        <td className="px-2 py-2"></td>
        <td className="px-2 py-2"></td>
        <td className={`px-2 py-2 ${W_DESC} ${sDescG}`}>
          <div className="flex items-center gap-2">
            <span
              title={bucketName}
              className={`text-zinc-800 dark:text-zinc-100 text-xs font-bold truncate ${italic ? "italic" : ""}`}
            >
              {bucketName}
            </span>
            <span className="text-[10px] font-semibold text-zinc-500 dark:text-zinc-400 px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/40">
              {lists.length}
            </span>
          </div>
        </td>
        <td className={`px-2 py-2 ${W_COPY} ${sCopyG}`}></td>
        <td className={`px-2 py-2 ${W_URL} ${sUrlG}`}></td>
        <td className={`px-2 py-2 ${W_SEND} ${sSendG}`}>
          <div className="flex items-center gap-1">
            {uniqSenders.slice(0, 2).map((s) => (
              <span
                key={s.name}
                title={s.name}
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded border"
                style={s.color ? { color: s.color, borderColor: s.color, backgroundColor: `${s.color}15` } : undefined}
              >
                {s.name}
              </span>
            ))}
            {uniqSenders.length > 2 && (
              <span className="text-[9px] text-zinc-500 font-semibold">+{uniqSenders.length - 2}</span>
            )}
          </div>
        </td>
        {METRIC_COLUMNS.map((col, idx) => {
          const isBase = (BASE_SUM_KEYS as readonly string[]).includes(col.key);
          const val = isBase ? summed[col.key] : 0;
          const show = isBase && val > 0;
          return (
            <td
              key={col.key}
              className={`px-2 py-2 text-right font-mono font-bold whitespace-nowrap ${
                show ? "text-zinc-800 dark:text-zinc-100" : "text-zinc-500"
              } ${isGroupBoundary(idx) ? GROUP_BOUNDARY_CLASSES : ""}`}
            >
              {show ? formatMetricValue(val, col) : ""}
            </td>
          );
        })}
      </tr>
    );
  };

  const nodes: ReactNode[] = [];

  // 1) Multi-list bucket groups
  for (const g of multi) {
    const key = `${w.id}::${g.bucketId}`;
    const collapsed = collapsedBuckets.has(key);
    nodes.push(renderGroupHeader(g.bucketId, g.bucketName, g.lists));
    if (!collapsed) g.lists.forEach((l) => nodes.push(renderListRow(l)));
  }

  // 2) "Unique Buckets" — synthetic group for single-list buckets
  if (single.length > 0) {
    const uniqueKey = "__unique__";
    const collapsed = collapsedBuckets.has(`${w.id}::${uniqueKey}`);
    nodes.push(renderGroupHeader(uniqueKey, "Unique Buckets", single, true));
    if (!collapsed) single.forEach((l) => nodes.push(renderListRow(l)));
  }

  // 3) Unbucketed lists (shouldn't normally exist but render safely)
  for (const l of unbucketed) nodes.push(renderListRow(l));

  // 4) Special rows (Nonjoiners / NO LIST DATA) — always visible, italic
  for (const l of specials) nodes.push(renderListRow(l));

  return nodes;
}


export function StatisticsPage() {
  const [webinars, setWebinars] = useState<ApiStatisticsWebinar[]>([]);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState<StatisticsMeta | null>(null);
  const [syncingWebinar, setSyncingWebinar] = useState<number | null>(null);
  const [collapsedBuckets, setCollapsedBuckets] = useState<Set<string>>(new Set());
  const [copyModalRow, setCopyModalRow] = useState<ApiStatisticsRow | null>(null);

  const toggleBucketGroup = (webinarId: string, groupKey: string) => {
    setCollapsedBuckets((prev) => {
      const key = `${webinarId}::${groupKey}`;
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleWebinarSync = async (webinarNumber: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (syncingWebinar !== null) return;
    setSyncingWebinar(webinarNumber);
    try {
      await triggerGhlWebinarSync(webinarNumber);
      alert(`Webinar ${webinarNumber} sync started. Track progress on the Sync page.`);
    } catch (err) {
      alert(err instanceof Error ? err.message : `Failed to start webinar ${webinarNumber} sync`);
    } finally {
      setSyncingWebinar(null);
    }
  };

  /* ── WebinarGeek sync ──────────────────────────────────────────── */
  const WG_PAGE = 5;
  const [wgBroadcasts, setWgBroadcasts] = useState<WgWebinar[]>([]);
  const [wgTotal, setWgTotal] = useState(0);
  const [wgOffset, setWgOffset] = useState(0);
  const [wgSelected, setWgSelected] = useState<string>("");
  const [wgSyncing, setWgSyncing] = useState(false);
  const [wgLoadingMore, setWgLoadingMore] = useState(false);
  const [wgMessage, setWgMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchWgWebinars({ limit: WG_PAGE, offset: 0 })
      .then(({ broadcasts, total }) => {
        setWgBroadcasts(broadcasts);
        setWgTotal(total);
        setWgOffset(broadcasts.length);
      })
      .catch(() => { /* connector not configured — silently skip */ });
  }, []);

  async function loadMoreWg() {
    if (wgLoadingMore || wgOffset >= wgTotal) return;
    setWgLoadingMore(true);
    try {
      const { broadcasts } = await fetchWgWebinars({ limit: WG_PAGE, offset: wgOffset });
      setWgBroadcasts((prev) => [...prev, ...broadcasts]);
      setWgOffset((prev) => prev + broadcasts.length);
    } finally {
      setWgLoadingMore(false);
    }
  }

  function formatWgDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString();
  }

  async function handleWgSync() {
    if (!wgSelected) return;
    setWgSyncing(true);
    setWgMessage(null);
    try {
      const res = await syncWgSubscribers(wgSelected);
      setWgMessage(`Synced ${res.total} subscribers.`);
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
            {wgBroadcasts.length > 0 && (
              <div className="flex items-center gap-2">
                <select
                  value={wgSelected}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "__load_more__") {
                      loadMoreWg();
                      return;
                    }
                    setWgSelected(v);
                    setWgMessage(null);
                  }}
                  className="bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500 max-w-[320px]"
                >
                  <option value="">WebinarGeek: select broadcast…</option>
                  {wgBroadcasts.map((w) => (
                    <option key={w.broadcast_id} value={w.broadcast_id}>
                      {w.internal_title ? `${w.internal_title} · ` : ""}{formatWgDate(w.starts_at)} · {w.broadcast_id}
                    </option>
                  ))}
                  {wgOffset < wgTotal && (
                    <option value="__load_more__">
                      {wgLoadingMore ? "Loading…" : `↓ Load more (${wgOffset}/${wgTotal})`}
                    </option>
                  )}
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
            {/* Row 1: Group spans (sticky top + already-sticky first cell on left) */}
            <tr className="bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-100 dark:border-zinc-800/20">
              <th colSpan={IDENTITY_COL_COUNT} className={`px-2 py-1 sticky ${TOP_BAND_ROW} ${L_DESC} ${Z_HEADER} ${BG_HEADER}`}></th>
              {METRIC_GROUPS.map((g) => (
                <th
                  key={g}
                  colSpan={columnsInGroup(g)}
                  className={`text-center px-1 py-1 text-[9px] font-bold uppercase tracking-wider text-zinc-400 border-l border-zinc-200 dark:border-zinc-800/30 sticky ${TOP_BAND_ROW} ${Z_HEADER} ${BG_HEADER}`}
                >
                  {g}
                </th>
              ))}
            </tr>
            {/* Row 2: Individual column labels (sticky top below row 1) */}
            <tr className="bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-200 dark:border-zinc-800/40">
              <th className={`w-8 px-2 py-2 sticky ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`}></th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[140px] sticky ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`}>Webinar #</th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] sticky ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`}>Status</th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[120px] sticky ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER}`}>Note</th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] ${W_DESC} ${sDescH}`}>Description</th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] ${W_COPY} ${sCopyH}`}>Copy</th>
              <th className={`text-center px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] ${W_URL} ${sUrlH}`}>URL</th>
              <th className={`text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] ${W_SEND} ${sSendH}`}>Send Info</th>
              {METRIC_COLUMNS.map((col, idx) => (
                <th
                  key={col.key}
                  className={`text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] whitespace-nowrap sticky ${TOP_LABEL_ROW} ${Z_HEADER} ${BG_HEADER} ${
                    isGroupBoundary(idx) ? GROUP_BOUNDARY_CLASSES : ""
                  }`}
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
                  <td className={`px-2 py-2.5 ${sDescP}`} colSpan={4}>
                    <button
                      onClick={(e) => handleWebinarSync(w.number, e)}
                      disabled={syncingWebinar !== null}
                      title={`Pull full GHL contact rows (contains e${w.number}) + opportunities for W${w.number}`}
                      className="px-2 py-1 text-[10px] font-semibold rounded bg-violet-500/15 text-violet-500 hover:bg-violet-500/25 border border-violet-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
                    >
                      {syncingWebinar === w.number ? (
                        <>
                          <div className="w-3 h-3 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                          Starting…
                        </>
                      ) : (
                        <>Sync GHL</>
                      )}
                    </button>
                  </td>
                  {METRIC_COLUMNS.map((col, idx) => (
                    <MetricCell
                      key={col.key}
                      value={w.summary[col.key]}
                      col={col}
                      bold
                      boundary={isGroupBoundary(idx)}
                      webinarNumber={w.number}
                      listLabel={`Webinar ${w.number}`}
                    />
                  ))}
                </tr>

                {/* ── Child rows (bucket-grouped) ─────────────────── */}
                {isExpanded && renderGroupedRows(w, collapsedBuckets, toggleBucketGroup, setCopyModalRow)}
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

      {/* ── Copy preview modal ─────────────────────────────────────── */}
      {copyModalRow && (
        <CopyModal row={copyModalRow} onClose={() => setCopyModalRow(null)} />
      )}
    </div>
  );
}
