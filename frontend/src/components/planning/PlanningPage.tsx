"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import {
  fetchBuckets, fetchSenders, fetchWebinars, fetchWebinarLists,
  assignBucketToWebinar, createWebinar as apiCreateWebinar,
  updateSender as apiUpdateSender, fetchBucketCopies, generateCopies,
  createSender as apiCreateSender,
  type ApiBucket, type ApiSender, type ApiWebinar, type ApiAssignment, type ApiCopy,
} from "@/lib/api";

/* ─── Types ────────────────────────────────────────────────────────────── */

// AvailableBucket now uses ApiBucket from API
type AvailableBucket = ApiBucket;

interface PlannedList {
  id: string;
  webinarId: string;
  bucket: string;
  description: string;
  listUrl: string;
  sender: string;
  dateSend: string;
  listSize: number;
  listRemain: number;
  gcalInvited: number;
  descVariant: string;
  title: string;
  accountsNeeded: number;
  industry: string;
  empRange: string;
  country: string;
  isNonjoiners?: boolean;
  isNoListData?: boolean;
  // Copy variants
  titleVariants?: { id: string; text: string; selected: boolean }[];
  descVariants?: { id: string; text: string; selected: boolean }[];
  copiesGenerated?: boolean;
  bucketId?: string;
  senderColor?: string;
}

interface Webinar {
  id: string;
  number: number;
  date: string;
  status: string;
  broadcastId: string;
  mainTitle: string;
  lists: PlannedList[];
  expanded: boolean;
  showAssignment: boolean;
}

interface Sender {
  id: string;
  name: string;
  accounts: number;
  sendPerAccount: number;
  daysPerWeek: number;
  color: string;
}

// Map API sender to local Sender interface
function apiSenderToLocal(s: ApiSender): Sender {
  return {
    id: s.id,
    name: s.name,
    accounts: s.total_accounts,
    sendPerAccount: s.send_per_account,
    daysPerWeek: s.days_per_webinar,
    color: s.color || "zinc",
  };
}

/* ─── Sender + Badge Helpers ───────────────────────────────────────────── */

// Map DB color names to Tailwind badge classes
const COLOR_CLASS_MAP: Record<string, string> = {
  violet: "bg-violet-500/15 text-violet-400 border-violet-500/25",
  blue: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  emerald: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  amber: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  cyan: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  rose: "bg-rose-500/15 text-rose-400 border-rose-500/25",
  orange: "bg-orange-500/15 text-orange-400 border-orange-500/25",
  teal: "bg-teal-500/15 text-teal-400 border-teal-500/25",
  pink: "bg-pink-500/15 text-pink-400 border-pink-500/25",
  indigo: "bg-indigo-500/15 text-indigo-400 border-indigo-500/25",
};
const DEFAULT_BADGE_CLS = "bg-zinc-200 dark:bg-zinc-700/30 text-zinc-600 dark:text-zinc-400 border-zinc-600/30";

function SenderBadge({ name, color }: { name: string; color?: string }) {
  if (!name) return <span className="text-zinc-600">—</span>;
  const cls = (color && COLOR_CLASS_MAP[color]) || DEFAULT_BADGE_CLS;
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>{name}</span>;
}

function VariantBadge({ variant }: { variant: string }) {
  if (!variant) return <span className="text-zinc-600">—</span>;
  const colors: Record<string, string> = {
    "c&a": "bg-amber-500/15 text-amber-400 border-amber-500/25",
    fin: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
    gen: "bg-violet-500/15 text-violet-300 border-violet-500/25",
    account: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  };
  const key = variant.toLowerCase().split(" ")[0];
  const cls = colors[key] || "bg-zinc-200 dark:bg-zinc-700/30 text-zinc-600 dark:text-zinc-400 border-zinc-600/30";
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>{variant}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { badge: string; dot: string }> = {
    planning: { badge: "bg-amber-500/10 text-amber-400 border-amber-500/20", dot: "bg-amber-400" },
    sent: { badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", dot: "bg-emerald-400" },
  };
  const c = colors[status.toLowerCase()] || { badge: "bg-zinc-200 dark:bg-zinc-700/30 text-zinc-600 dark:text-zinc-400 border-zinc-600/30", dot: "bg-zinc-400" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {status}
    </span>
  );
}

/* ─── Data is now loaded from API ──────────────────────────────────────── */

// Helper: convert ApiAssignment to PlannedList
function apiAssignmentToList(a: ApiAssignment): PlannedList {
  return {
    id: a.id,
    webinarId: a.webinar_id,
    bucket: a.bucket?.name || "—",
    description: a.description || "",
    listUrl: a.list_url || "",
    sender: a.sender?.name || "",
    senderColor: a.sender?.color || undefined,
    dateSend: "",
    listSize: a.volume,
    listRemain: a.remaining,
    gcalInvited: a.gcal_invited,
    descVariant: "",
    title: a.title_copy?.text || "",
    accountsNeeded: a.accounts_used,
    industry: a.bucket?.industry || "",
    empRange: a.emp_range_override || "",
    country: a.countries_override || "",
    isNonjoiners: a.is_nonjoiners,
    isNoListData: a.is_no_list_data,
    copiesGenerated: !!a.title_copy,
    bucketId: a.bucket?.id,
    titleVariants: a.title_copy ? [{ id: a.title_copy.id, text: a.title_copy.text, selected: true }] : undefined,
    descVariants: a.desc_copy ? [{ id: a.desc_copy.id, text: a.desc_copy.text, selected: true }] : undefined,
  };
}

/* ─── Custom Dropdown ──────────────────────────────────────────────────── */

interface DropdownOption {
  value: string;
  label: string;
}

function Dropdown({
  options,
  value,
  onChange,
  placeholder = "Select...",
  className = "",
}: {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-sm text-left flex items-center justify-between gap-2 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-colors"
      >
        <span className={selected ? "text-zinc-800 dark:text-zinc-200 truncate" : "text-zinc-500 truncate"}>
          {selected ? selected.label : placeholder}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          className={`text-zinc-500 shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg shadow-xl shadow-black/10 dark:shadow-black/40 max-h-[240px] overflow-y-auto py-1">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => { onChange(o.value); setOpen(false); }}
              className={`w-full text-left px-3 py-1.5 text-sm transition-colors ${
                o.value === value
                  ? "bg-violet-500/10 text-violet-600 dark:text-violet-400 font-medium"
                  : "text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/60"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────────────────── */

export function PlanningPage() {
  const [buckets, setBuckets] = useState<AvailableBucket[]>([]);
  const [senders, setSenders] = useState<Sender[]>([]);
  const [editingSenders, setEditingSenders] = useState(false);
  const [webinars, setWebinars] = useState<Webinar[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loadingData, setLoadingData] = useState(true);

  /* ── Load all data from API on mount ──────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      try {
        const [bucketsRes, sendersRes, webinarsRes] = await Promise.all([
          fetchBuckets(), fetchSenders(), fetchWebinars(),
        ]);
        if (cancelled) return;

        setBuckets(bucketsRes.buckets);
        setSenders(sendersRes.senders.map(apiSenderToLocal));

        // Load assignments for each webinar
        const webinarList: Webinar[] = [];
        const allAssignments: ApiAssignment[] = [];
        for (const w of webinarsRes.webinars) {
          const d = new Date(w.date + "T00:00:00");
          const dateStr = d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
          let lists: PlannedList[] = [];
          try {
            const { assignments } = await fetchWebinarLists(w.id);
            allAssignments.push(...assignments);
            lists = assignments.map(apiAssignmentToList);
          } catch { /* no lists yet */ }
          webinarList.push({
            id: w.id,
            number: w.number,
            date: dateStr,
            status: w.status.charAt(0).toUpperCase() + w.status.slice(1),
            broadcastId: w.broadcast_id || "—",
            mainTitle: w.main_title || "",
            lists,
            expanded: w.status === "planning",
            showAssignment: w.status === "planning",
          });
        }

        // Load all copy variants for each unique bucket used in assignments
        const uniqueBucketIds = [...new Set(allAssignments.filter(a => a.bucket).map(a => a.bucket!.id))];
        const bucketCopiesMap: Record<string, { titles: ApiCopy[]; descriptions: ApiCopy[] }> = {};
        await Promise.all(uniqueBucketIds.map(async (bucketId) => {
          try {
            const copies = await fetchBucketCopies(bucketId);
            bucketCopiesMap[bucketId] = { titles: copies.titles, descriptions: copies.descriptions };
          } catch { /* no copies yet */ }
        }));

        // Enrich lists with all copy variants from their bucket
        for (const w of webinarList) {
          w.lists = w.lists.map((l) => {
            if (!l.bucketId || !bucketCopiesMap[l.bucketId]) return l;
            const copies = bucketCopiesMap[l.bucketId];
            const selectedTitleId = l.titleVariants?.[0]?.id;
            const selectedDescId = l.descVariants?.[0]?.id;
            return {
              ...l,
              copiesGenerated: copies.titles.length > 0 || copies.descriptions.length > 0,
              titleVariants: copies.titles.map((c) => ({
                id: c.id, text: c.text, selected: c.id === selectedTitleId || (!selectedTitleId && c.is_primary),
              })),
              descVariants: copies.descriptions.map((c) => ({
                id: c.id, text: c.text, selected: c.id === selectedDescId || (!selectedDescId && c.is_primary),
              })),
              title: (() => {
                if (selectedTitleId) {
                  const match = copies.titles.find(c => c.id === selectedTitleId);
                  if (match) return match.text;
                }
                const primary = copies.titles.find(c => c.is_primary);
                return primary?.text || l.title;
              })(),
            };
          });
        }

        setWebinars(webinarList);
        // Default assignment target to first planning webinar
        const planningW = webinarList.find(w => w.status.toLowerCase() === "planning");
        if (planningW) setAssignWebinar(planningW.id);
      } catch (err) {
        console.error("Failed to load data:", err);
      } finally {
        if (!cancelled) setLoadingData(false);
      }
    }
    loadData();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [searchQuery, setSearchQuery] = useState("");
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copyModalLists, setCopyModalLists] = useState<PlannedList[]>([]);
  const [generatingCopies, setGeneratingCopies] = useState(false);
  const [planningCopyModal, setPlanningCopyModal] = useState<{ listId: string; webinarId: string; tab: "title" | "description" } | null>(null);

  // New Webinar modal state
  const [showNewWebinarModal, setShowNewWebinarModal] = useState(false);
  const getNextWebinarDefaults = useCallback(() => {
    const maxWebinar = webinars.reduce((max, w) => w.number > max.number ? w : max, webinars[0]);
    const nextNumber = maxWebinar ? maxWebinar.number + 1 : 1;
    // Parse the date string and add 7 days
    let nextDate = "";
    if (maxWebinar) {
      const d = new Date(maxWebinar.date);
      if (!isNaN(d.getTime())) {
        d.setDate(d.getDate() + 7);
        nextDate = d.toISOString().split("T")[0]; // YYYY-MM-DD for input[type=date]
      }
    }
    if (!nextDate) {
      const d = new Date();
      d.setDate(d.getDate() + 7);
      nextDate = d.toISOString().split("T")[0];
    }
    return { nextNumber, nextDate };
  }, [webinars]);
  const [newWebinarNumber, setNewWebinarNumber] = useState(0);
  const [newWebinarDate, setNewWebinarDate] = useState("");

  // Assignment form state
  const [assignBucket, setAssignBucket] = useState("");
  const [assignSender, setAssignSender] = useState("");
  const [assignVolume, setAssignVolume] = useState(0);
  const [assignWebinar, setAssignWebinar] = useState("");
  // Assignment filter overrides (pre-filled from bucket, editable)
  const [assignCountries, setAssignCountries] = useState("");
  const [assignEmpRange, setAssignEmpRange] = useState("");
  const [assignAccounts, setAssignAccounts] = useState(0);
  const [assignSendPerAcct, setAssignSendPerAcct] = useState(0);
  const [assignDays, setAssignDays] = useState(5);

  // New Sender form state
  const [showNewSenderForm, setShowNewSenderForm] = useState(false);
  const [newSenderName, setNewSenderName] = useState("");
  const [newSenderAccounts, setNewSenderAccounts] = useState(5);
  const [newSenderSendPerAcct, setNewSenderSendPerAcct] = useState(50);
  const [newSenderDaysPerWeb, setNewSenderDaysPerWeb] = useState(5);
  const [creatingSender, setCreatingSender] = useState(false);

  const updateSender = async (id: string, field: keyof Sender, value: number) => {
    // Optimistic update
    setSenders((prev) => prev.map((s) => s.id === id ? { ...s, [field]: value } : s));
    // Map local field names to API field names
    const apiFieldMap: Record<string, string> = {
      accounts: "total_accounts",
      sendPerAccount: "send_per_account",
      daysPerWeek: "days_per_webinar",
    };
    const apiField = apiFieldMap[field] || field;
    try {
      await apiUpdateSender(id, { [apiField]: value });
    } catch (err) {
      console.error("Failed to update sender:", err);
    }
  };

  const handleAddSender = async () => {
    if (!newSenderName.trim()) return;
    setCreatingSender(true);
    try {
      const created = await apiCreateSender({
        name: newSenderName.trim(),
        total_accounts: newSenderAccounts,
        send_per_account: newSenderSendPerAcct,
        days_per_webinar: newSenderDaysPerWeb,
      });
      setSenders(prev => [...prev, apiSenderToLocal(created)]);
      setNewSenderName("");
      setNewSenderAccounts(5);
      setNewSenderSendPerAcct(50);
      setNewSenderDaysPerWeb(5);
      setShowNewSenderForm(false);
    } catch (err) {
      console.error("Failed to create sender:", err);
      alert(err instanceof Error ? err.message : "Failed to create sender");
    } finally {
      setCreatingSender(false);
    }
  };

  /* ── Stats ─────────────────────────────────────────────────────────── */

  const globalStats = useMemo(() => {
    const allLists = webinars.flatMap((w) => w.lists.filter((l) => !l.isNonjoiners && !l.isNoListData));
    return {
      totalLists: allLists.length,
      totalVolume: allLists.reduce((s, l) => s + l.listSize, 0),
      totalRemaining: allLists.reduce((s, l) => s + l.listRemain, 0),
      totalAccounts: Math.round(allLists.reduce((s, l) => s + l.accountsNeeded, 0)),
      availableBuckets: buckets.reduce((s, b) => s + (b.remaining_contacts || 0), 0),
    };
  }, [webinars, buckets]);

  /* ── Account tracking per sender per webinar ────────────────────────── */

  const getAccountsUsedForSender = useCallback((webinarId: string, senderId: string): number => {
    const w = webinars.find((w) => w.id === webinarId);
    if (!w) return 0;
    const sender = senders.find((s) => s.id === senderId);
    if (!sender) return 0;
    return Math.round(
      w.lists
        .filter((l) => !l.isNonjoiners && !l.isNoListData && l.sender.toLowerCase() === sender.name.toLowerCase())
        .reduce((sum, l) => sum + l.accountsNeeded, 0)
    );
  }, [webinars, senders]);

  const getAvailableAccounts = useCallback((webinarId: string, senderId: string): number => {
    const sender = senders.find((s) => s.id === senderId);
    if (!sender) return 0;
    const used = getAccountsUsedForSender(webinarId, senderId);
    return Math.max(0, sender.accounts - used);
  }, [senders, getAccountsUsedForSender]);

  /* ── Handlers ──────────────────────────────────────────────────────── */

  const toggleWebinar = (id: string) => {
    setWebinars((prev) => prev.map((w) => (w.id === id ? { ...w, expanded: !w.expanded } : w)));
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAllInWebinar = (webinarId: string) => {
    const w = webinars.find((w) => w.id === webinarId);
    if (!w) return;
    const listIds = w.lists.filter((l) => !l.isNonjoiners && !l.isNoListData).map((l) => l.id);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const allSelected = listIds.every((id) => next.has(id));
      if (allSelected) listIds.forEach((id) => next.delete(id));
      else listIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const handleAssign = useCallback(async () => {
    if (!assignBucket || !assignSender || assignVolume <= 0 || !assignWebinar) return;
    const bucket = buckets.find((b) => b.id === assignBucket);
    const sender = senders.find((s) => s.id === assignSender);
    if (!bucket || !sender) return;

    const volume = Math.min(assignVolume, bucket.remaining_contacts);
    const sendPerAcct = assignSendPerAcct > 0 ? assignSendPerAcct : sender.sendPerAccount;
    const accts = assignAccounts > 0 ? assignAccounts : Math.ceil(volume / (sendPerAcct * assignDays));

    const countries = assignCountries || (bucket.countries || []).join(", ");
    const empRange = assignEmpRange || bucket.emp_range || "";

    try {
      const assignment = await assignBucketToWebinar(assignWebinar, {
        bucket_id: assignBucket,
        sender_id: assignSender,
        volume,
        accounts_used: accts,
        send_per_account: sendPerAcct,
        days: assignDays,
        countries_override: countries,
        emp_range_override: empRange,
      });

      // Add to webinar in local state
      const newList = apiAssignmentToList(assignment);
      setWebinars((prev) => prev.map((w) =>
        w.id === assignWebinar ? { ...w, lists: [...w.lists, newList] } : w
      ));

      // Decrease bucket remaining
      setBuckets((prev) => prev.map((b) =>
        b.id === assignBucket ? { ...b, remaining_contacts: b.remaining_contacts - volume } : b
      ));

      // Reset form
      setAssignBucket("");
      setAssignSender("");
      setAssignVolume(0);
      setAssignCountries("");
      setAssignEmpRange("");
      setAssignAccounts(0);
      setAssignSendPerAcct(0);
      setAssignDays(5);
    } catch (err) {
      console.error("Failed to assign:", err);
      alert(err instanceof Error ? err.message : "Failed to assign bucket");
    }
  }, [assignBucket, assignSender, assignVolume, assignWebinar, assignCountries, assignEmpRange, assignAccounts, assignSendPerAcct, assignDays, buckets, senders]);

  const openCopyModal = () => {
    const lists = webinars.flatMap((w) => w.lists).filter((l) => selectedIds.has(l.id) && !l.isNonjoiners && !l.isNoListData);
    setCopyModalLists(lists);
    setShowCopyModal(true);
  };

  const handleGenerateCopies = async () => {
    setGeneratingCopies(true);
    try {
      // Find unique bucket IDs from selected lists
      const uniqueBucketIds = [...new Set(
        copyModalLists.filter((l) => l.bucketId).map((l) => l.bucketId!)
      )];

      // Generate copies for each bucket (both title + description)
      const bucketCopiesMap: Record<string, { titles: ApiCopy[]; descriptions: ApiCopy[] }> = {};
      await Promise.all(uniqueBucketIds.map(async (bucketId) => {
        const result = await generateCopies(bucketId, { copy_type: "both" });
        bucketCopiesMap[bucketId] = { titles: result.titles, descriptions: result.descriptions };
      }));

      // Update lists with generated copies
      const updateList = (l: PlannedList): PlannedList => {
        if (!l.bucketId || !bucketCopiesMap[l.bucketId]) return l;
        const copies = bucketCopiesMap[l.bucketId];
        const primaryTitle = copies.titles.find((c) => c.is_primary);
        return {
          ...l,
          copiesGenerated: true,
          title: primaryTitle?.text || l.title,
          titleVariants: copies.titles.map((c) => ({ id: c.id, text: c.text, selected: c.is_primary })),
          descVariants: copies.descriptions.map((c) => ({ id: c.id, text: c.text, selected: c.is_primary })),
        };
      };

      setWebinars((prev) => prev.map((w) => ({
        ...w,
        lists: w.lists.map((l) => (copyModalLists.some((ml) => ml.id === l.id) ? updateList(l) : l)),
      })));
      setCopyModalLists((prev) => prev.map(updateList));
    } catch (err) {
      console.error("Failed to generate copies:", err);
      alert(err instanceof Error ? err.message : "Failed to generate copies");
    } finally {
      setGeneratingCopies(false);
    }
  };

  const selectVariant = (listId: string, type: "title" | "desc", variantId: string) => {
    setWebinars((prev) => prev.map((w) => ({
      ...w,
      lists: w.lists.map((l) => {
        if (l.id !== listId) return l;
        if (type === "title") {
          const selected = l.titleVariants?.find((v) => v.id === variantId);
          return {
            ...l,
            title: selected?.text || l.title,
            titleVariants: l.titleVariants?.map((v) => ({ ...v, selected: v.id === variantId })),
          };
        } else {
          return {
            ...l,
            descVariants: l.descVariants?.map((v) => ({ ...v, selected: v.id === variantId })),
            descVariant: l.descVariants?.find((v) => v.id === variantId)?.text.substring(0, 20) + "..." || l.descVariant,
          };
        }
      }),
    })));
    // Also update modal
    setCopyModalLists((prev) => prev.map((l) => {
      if (l.id !== listId) return l;
      if (type === "title") {
        const selected = l.titleVariants?.find((v) => v.id === variantId);
        return {
          ...l,
          title: selected?.text || l.title,
          titleVariants: l.titleVariants?.map((v) => ({ ...v, selected: v.id === variantId })),
        };
      } else {
        return {
          ...l,
          descVariants: l.descVariants?.map((v) => ({ ...v, selected: v.id === variantId })),
        };
      }
    }));
  };

  const closeCopyModal = () => {
    setShowCopyModal(false);
    setSelectedIds(new Set());
  };

  const openNewWebinarModal = () => {
    const { nextNumber, nextDate } = getNextWebinarDefaults();
    setNewWebinarNumber(nextNumber);
    setNewWebinarDate(nextDate);
    setShowNewWebinarModal(true);
  };

  const handleCreateWebinar = async () => {
    if (!newWebinarNumber || !newWebinarDate) return;
    try {
      const created = await apiCreateWebinar({ number: newWebinarNumber, date: newWebinarDate });
      const d = new Date(newWebinarDate + "T00:00:00");
      const dateStr = d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
      const newWebinar: Webinar = {
        id: created.id,
        number: created.number,
        date: dateStr,
        status: "Planning",
        broadcastId: "—",
        mainTitle: "",
        lists: [],
        expanded: true,
        showAssignment: true,
      };
      setWebinars((prev) => [newWebinar, ...prev]);
      setAssignWebinar(created.id);
      setShowNewWebinarModal(false);
    } catch (err) {
      console.error("Failed to create webinar:", err);
      alert(err instanceof Error ? err.message : "Failed to create webinar");
    }
  };

  /* ── Filtered webinars ─────────────────────────────────────────────── */

  const filteredWebinars = useMemo(() => {
    if (!searchQuery) return webinars;
    const q = searchQuery.toLowerCase();
    return webinars.filter((w) =>
      w.number.toString().includes(q) ||
      w.date.toLowerCase().includes(q) ||
      w.lists.some((l) => l.description.toLowerCase().includes(q) || l.bucket.toLowerCase().includes(q) || l.sender.toLowerCase().includes(q))
    );
  }, [webinars, searchQuery]);

  const selectedCount = selectedIds.size;

  /* ── Render ────────────────────────────────────────────────────────── */

  return (
    <main className="min-h-screen pb-20">
      {/* ── Sticky header ──────────────────────────────────────────── */}
      <div className="sticky top-12 z-40 bg-white dark:bg-zinc-950/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800/40 px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Campaign Planning</h1>
            <div className="flex gap-2">
              {[
                { label: "Lists", value: globalStats.totalLists, color: "text-zinc-800 dark:text-zinc-200" },
                { label: "Volume", value: globalStats.totalVolume.toLocaleString(), color: "text-violet-400" },
                { label: "Available", value: globalStats.availableBuckets.toLocaleString(), color: "text-amber-400" },
                { label: "Accounts", value: globalStats.totalAccounts, color: "text-emerald-400" },
              ].map((s) => (
                <div key={s.label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/40">
                  <span className={`text-sm font-bold font-mono ${s.color}`}>{s.value}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search lists, buckets, senders..." className="w-56 bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500" />
            <button onClick={openNewWebinarModal} className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
              New Webinar
            </button>
          </div>
        </div>
      </div>

      {/* Sender legend — editable */}
      <div className="px-6 py-2 border-b border-zinc-200 dark:border-zinc-800/20 bg-white dark:bg-zinc-950/50">
        <div className="flex items-center gap-2 mb-0">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Senders:</span>
          <button onClick={() => setEditingSenders(!editingSenders)} className="text-[10px] text-zinc-600 hover:text-zinc-600 dark:text-zinc-400 transition-colors ml-1">
            {editingSenders ? "Done" : "Edit"}
          </button>
        </div>
        {!editingSenders ? (
          <div className="flex items-center gap-4 mt-1">
            {senders.map((s) => (
              <div key={s.id} className="flex items-center gap-1.5">
                <SenderBadge name={s.name} color={s.color} />
                <span className="text-[10px] text-zinc-500 font-mono">{s.accounts} accts · {s.sendPerAccount}/acct · {s.daysPerWeek}d/webinar</span>
                <span className="text-[10px] text-zinc-600 font-mono">= {(s.accounts * s.sendPerAccount).toLocaleString()}/d</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-5 mt-2">
            {senders.map((s) => (
              <div key={s.id} className="flex items-center gap-2 bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/40 rounded-lg px-3 py-2">
                <input
                  type="text"
                  defaultValue={s.name}
                  onBlur={(e) => {
                    const newName = e.target.value.trim();
                    if (newName && newName !== s.name) {
                      setSenders(prev => prev.map(x => x.id === s.id ? { ...x, name: newName } : x));
                      apiUpdateSender(s.id, { name: newName }).catch(err => console.error("Failed to rename sender:", err));
                    }
                  }}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                  className="w-20 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-semibold focus:outline-none focus:ring-1 focus:ring-violet-500"
                />
                <div className="flex items-center gap-1.5">
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Accts</span>
                    <input type="number" key={`accts-${s.id}-${s.accounts}`} defaultValue={s.accounts}
                      onBlur={(e) => { const v = parseInt(e.target.value) || 0; if (v !== s.accounts) updateSender(s.id, "accounts", v); }}
                      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      className="w-12 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                  <span className="text-zinc-600 text-[10px]">×</span>
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Send/Acct</span>
                    <input type="number" key={`spa-${s.id}-${s.sendPerAccount}`} defaultValue={s.sendPerAccount}
                      onBlur={(e) => { const v = parseInt(e.target.value) || 0; if (v !== s.sendPerAccount) updateSender(s.id, "sendPerAccount", v); }}
                      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      className="w-12 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                  <span className="text-zinc-600 text-[10px]">×</span>
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Days/Web</span>
                    <input type="number" key={`dpw-${s.id}-${s.daysPerWeek}`} defaultValue={s.daysPerWeek}
                      onBlur={(e) => { const v = parseInt(e.target.value) || 0; if (v !== s.daysPerWeek) updateSender(s.id, "daysPerWeek", v); }}
                      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                      className="w-12 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                  <span className="text-zinc-600 text-[10px]">=</span>
                  <span className="text-[11px] text-violet-400 font-mono font-bold">{(s.accounts * s.sendPerAccount).toLocaleString()}/d</span>
                </div>
              </div>
            ))}

            {/* Add Sender button / form */}
            {!showNewSenderForm ? (
              <button
                onClick={() => setShowNewSenderForm(true)}
                className="flex items-center gap-1.5 px-3 py-2 border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg text-[11px] text-zinc-500 hover:text-violet-400 hover:border-violet-500/40 transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                Add Sender
              </button>
            ) : (
              <div className="flex items-center gap-2 bg-violet-50 dark:bg-violet-500/5 border border-violet-200 dark:border-violet-500/20 rounded-lg px-3 py-2">
                <div className="flex flex-col">
                  <span className="text-[8px] text-zinc-600 uppercase">Name</span>
                  <input
                    type="text"
                    value={newSenderName}
                    onChange={(e) => setNewSenderName(e.target.value)}
                    placeholder="Name..."
                    autoFocus
                    className="w-20 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
                  />
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Accts</span>
                    <input type="number" value={newSenderAccounts} onChange={(e) => setNewSenderAccounts(parseInt(e.target.value) || 0)}
                      className="w-12 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                  <span className="text-zinc-600 text-[10px]">×</span>
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Send/Acct</span>
                    <input type="number" value={newSenderSendPerAcct} onChange={(e) => setNewSenderSendPerAcct(parseInt(e.target.value) || 0)}
                      className="w-12 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                  <span className="text-zinc-600 text-[10px]">×</span>
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] text-zinc-600 uppercase">Days/Web</span>
                    <input type="number" value={newSenderDaysPerWeb} onChange={(e) => setNewSenderDaysPerWeb(parseInt(e.target.value) || 0)}
                      className="w-12 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                  </div>
                </div>
                <button
                  onClick={handleAddSender}
                  disabled={!newSenderName.trim() || creatingSender}
                  className="px-3 py-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-[10px] font-semibold rounded-md transition-colors"
                >
                  {creatingSender ? "Adding..." : "Add"}
                </button>
                <button
                  onClick={() => setShowNewSenderForm(false)}
                  className="text-[10px] text-zinc-400 hover:text-zinc-600 transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Webinar table ──────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[1600px]">
          <thead>
            <tr className="bg-zinc-50 dark:bg-zinc-900/90 border-b border-zinc-200 dark:border-zinc-800/40">
              <th className="w-8 px-2 py-2"></th>
              <th className="w-8 px-1 py-2"></th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Webinar #</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Status</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[320px]">Description of List</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Bucket</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Sender</th>
              <th className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">List Size</th>
              <th className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Remaining</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[250px]">Title</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[250px]">Description</th>
              <th className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Accts</th>
              <th className="text-center px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Copies</th>
            </tr>
          </thead>
          {filteredWebinars.map((w) => {
              const wLists = w.lists.filter((l) => !l.isNonjoiners && !l.isNoListData);
              const wTotal = wLists.reduce((s, l) => s + l.listSize, 0);
              const wRemain = w.lists.reduce((s, l) => s + l.listRemain, 0);
              const wAccounts = Math.round(wLists.reduce((s, l) => s + l.accountsNeeded, 0));
              const allInWebinarSelected = wLists.length > 0 && wLists.every((l) => selectedIds.has(l.id));

              return (
                <tbody key={w.id}>
                  {/* ── Webinar parent row ─────────────────────────── */}
                  <tr className="bg-zinc-100 dark:bg-zinc-800/40 hover:bg-zinc-200 dark:hover:bg-zinc-800/60 cursor-pointer border-t-2 border-zinc-300 dark:border-zinc-700/40 transition-colors">
                    <td className="px-2 py-2.5 text-center" onClick={() => toggleWebinar(w.id)}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                        className={`text-zinc-600 dark:text-zinc-400 transition-transform duration-200 ${w.expanded ? "rotate-90" : ""}`}>
                        <path d="M9 18l6-6-6-6"/>
                      </svg>
                    </td>
                    <td className="px-1 py-2.5">
                      {wLists.length > 0 && (
                        <div onClick={() => selectAllInWebinar(w.id)} className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center cursor-pointer transition-colors ${
                          allInWebinarSelected ? "bg-violet-600 border-violet-600" : "border-zinc-600 hover:border-zinc-500"
                        }`}>
                          {allInWebinarSelected && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><path d="M20 6L9 17l-5-5"/></svg>}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2.5" onClick={() => toggleWebinar(w.id)}>
                      <span className="text-zinc-900 dark:text-zinc-100 font-bold text-sm">{w.number}</span>
                      <span className="text-zinc-500 ml-2">{w.date}</span>
                    </td>
                    <td className="px-2 py-2.5"><StatusBadge status={w.status} /></td>
                    <td className="px-2 py-2.5" colSpan={3} onClick={() => toggleWebinar(w.id)}>
                      <span className="text-zinc-800 dark:text-zinc-300 font-medium text-[11px]">{w.mainTitle || `${wLists.length} lists assigned`}</span>
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-zinc-800 dark:text-zinc-200 font-bold">{wTotal > 0 ? wTotal.toLocaleString() : ""}</td>
                    <td className="px-2 py-2.5 text-right font-mono text-violet-400 font-bold">{wRemain > 0 ? wRemain.toLocaleString() : ""}</td>
                    <td className="px-2 py-2.5" colSpan={2}></td>
                    <td className="px-2 py-2.5 text-right font-mono text-emerald-400 font-bold">{wAccounts > 0 ? wAccounts : ""}</td>
                    <td className="px-2 py-2.5"></td>
                  </tr>

                  {/* ── Assignment section (for Planning webinars) ──── */}
                  {w.expanded && w.showAssignment && (
                    <tr>
                      <td colSpan={13} className="p-0">
                        <div className="relative z-20 bg-zinc-50 dark:bg-zinc-900/40 border-y border-zinc-200 dark:border-zinc-800/30 px-6 py-4">
                          <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider">Assign Buckets to W{w.number}</span>
                            <span className="text-[10px] text-zinc-500">{buckets.filter((b) => b.remaining_contacts > 0).length} buckets available · {buckets.reduce((s, b) => s + (b.remaining_contacts || 0), 0).toLocaleString()} contacts</span>
                          </div>

                          {/* Assignment form — row 1: bucket + sender + volume */}
                          <div className="flex items-end gap-3 mb-2">
                            <div className="flex-1 min-w-[200px]">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Bucket</label>
                              <Dropdown
                                placeholder="Select bucket..."
                                value={assignBucket}
                                onChange={(val) => {
                                  setAssignBucket(val);
                                  const b = buckets.find((b) => b.id === val);
                                  if (b) {
                                    setAssignVolume(b.remaining_contacts);
                                    setAssignCountries((b.countries || []).join(", "));
                                    setAssignEmpRange(b.emp_range || "");
                                    setAssignAccounts(0);
                                    setAssignDays(5);
                                  }
                                }}
                                options={buckets.filter((b) => b.remaining_contacts > 0).map((b) => ({
                                  value: b.id,
                                  label: `${b.name} (${b.remaining_contacts.toLocaleString()} remaining)`,
                                }))}
                              />
                            </div>
                            <div className="w-56">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Sender</label>
                              <Dropdown
                                placeholder="Select..."
                                value={assignSender}
                                onChange={(val) => {
                                  setAssignSender(val);
                                  // Auto-set accounts to remaining available
                                  const avail = getAvailableAccounts(w.id, val);
                                  setAssignAccounts(0); // reset to use available
                                }}
                                options={senders.map((s) => {
                                  const used = getAccountsUsedForSender(w.id, s.id);
                                  const avail = s.accounts - used;
                                  return {
                                    value: s.id,
                                    label: `${s.name} (${avail}/${s.accounts} accts free)`,
                                  };
                                })}
                              />
                            </div>
                            <div className="w-28">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Volume</label>
                              <input type="number" value={assignVolume || ""} onChange={(e) => setAssignVolume(parseInt(e.target.value) || 0)} className="w-full bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-violet-500" />
                            </div>
                            <button onClick={handleAssign} disabled={!assignBucket || !assignSender || assignVolume <= 0}
                              className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-200 dark:bg-zinc-700 disabled:text-zinc-500 text-white text-xs font-semibold rounded-lg transition-colors whitespace-nowrap">
                              Assign →
                            </button>
                          </div>

                          {/* Assignment form — row 2: sending config (shown when bucket + sender selected) */}
                          {assignBucket && assignSender && (() => {
                            const s = senders.find((s) => s.id === assignSender);
                            if (!s) return null;
                            const usedAccts = getAccountsUsedForSender(w.id, s.id);
                            const availAccts = Math.max(0, s.accounts - usedAccts);
                            const accts = assignAccounts > 0 ? assignAccounts : availAccts;
                            const sendPerAcct = assignSendPerAcct > 0 ? assignSendPerAcct : s.sendPerAccount;
                            const dailyCap = accts * sendPerAcct;
                            const totalPerWebinar = dailyCap * assignDays;
                            const sendingDays = dailyCap > 0 ? Math.ceil(assignVolume / dailyCap) : 0;
                            const overAllocated = accts > availAccts;
                            return (
                              <div className="space-y-2 mb-4">
                                {/* Account availability indicator */}
                                <div className="flex items-center gap-3">
                                  <div className="flex items-center gap-2">
                                    <SenderBadge name={s.name} color={s.color} />
                                    <div className="flex items-center gap-1.5">
                                      <span className="text-[10px] text-zinc-500">Accounts:</span>
                                      <span className={`text-[11px] font-mono font-bold ${availAccts === 0 ? 'text-red-400' : availAccts <= 2 ? 'text-amber-400' : 'text-emerald-400'}`}>
                                        {availAccts}
                                      </span>
                                      <span className="text-[10px] text-zinc-500">/ {s.accounts} available</span>
                                      {usedAccts > 0 && (
                                        <span className="text-[9px] text-zinc-500 bg-zinc-100 dark:bg-zinc-800/60 px-1.5 py-0.5 rounded border border-zinc-300 dark:border-zinc-700/30">
                                          {usedAccts} used in W{w.number}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                  {/* Account usage bar */}
                                  <div className="flex-1 max-w-[120px]">
                                    <div className="h-1.5 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                                      <div
                                        className={`h-full rounded-full transition-all ${usedAccts / s.accounts > 0.8 ? 'bg-red-400' : usedAccts / s.accounts > 0.5 ? 'bg-amber-400' : 'bg-emerald-400'}`}
                                        style={{ width: `${Math.min(100, (usedAccts / s.accounts) * 100)}%` }}
                                      />
                                    </div>
                                  </div>
                                </div>

                                {/* Sending config */}
                                <div className="flex items-center gap-3">
                                  <div className="flex items-center gap-2 bg-zinc-100 dark:bg-zinc-800/40 border border-zinc-300 dark:border-zinc-700/30 rounded-lg px-3 py-2">
                                    <div className="flex items-center gap-1.5">
                                      <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-zinc-600 uppercase">Accts</span>
                                        <input type="number" value={accts} onChange={(e) => setAssignAccounts(parseInt(e.target.value) || 0)}
                                          className={`w-12 bg-zinc-100 dark:bg-zinc-800 border rounded px-1.5 py-0.5 text-[11px] font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500 ${
                                            overAllocated ? 'border-red-400 text-red-400' : 'border-zinc-300 dark:border-zinc-700/60 text-zinc-800 dark:text-zinc-200'
                                          }`} />
                                      </div>
                                      <span className="text-zinc-600 text-[10px]">×</span>
                                      <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-zinc-600 uppercase">Send/Acct</span>
                                        <input type="number" value={sendPerAcct} onChange={(e) => setAssignSendPerAcct(parseInt(e.target.value) || 0)}
                                          className="w-12 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                                      </div>
                                      <span className="text-zinc-600 text-[10px]">=</span>
                                      <span className="text-[11px] text-violet-400 font-mono font-bold">{dailyCap.toLocaleString()}/d</span>
                                      <span className="text-zinc-600 text-[10px]">×</span>
                                      <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-zinc-600 uppercase">Days/Web</span>
                                        <input type="number" value={assignDays} onChange={(e) => setAssignDays(parseInt(e.target.value) || 5)}
                                          className="w-12 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500" />
                                      </div>
                                      <span className="text-zinc-600 text-[10px]">=</span>
                                      <span className="text-[11px] text-violet-400 font-mono font-bold">{totalPerWebinar.toLocaleString()}/web</span>
                                    </div>
                                  </div>
                                  <div className="flex flex-col gap-0.5">
                                    <span className="text-[10px] text-zinc-500">≈ {sendingDays} sending day{sendingDays !== 1 ? 's' : ''} to send {assignVolume.toLocaleString()} contacts</span>
                                    {overAllocated && (
                                      <span className="text-[10px] text-red-400 font-medium">⚠ Exceeds available accounts by {accts - availAccts}</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })()}

                          {/* Available buckets mini-table */}
                          <div className="rounded-lg border border-zinc-200 dark:border-zinc-800/40 overflow-hidden max-h-[200px] overflow-y-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="bg-zinc-100 dark:bg-zinc-800/40">
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Bucket</th>
                                  <th className="text-right px-3 py-1.5 text-zinc-500 font-medium">Total</th>
                                  <th className="text-right px-3 py-1.5 text-zinc-500 font-medium">Remaining</th>
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Countries</th>
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Emp Range</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-zinc-800/20">
                                {buckets.filter((b) => b.remaining_contacts > 0).map((b) => (
                                  <tr key={b.id} onClick={() => { setAssignBucket(b.id); setAssignVolume(b.remaining_contacts); setAssignCountries((b.countries || []).join(", ")); setAssignEmpRange(b.emp_range || ""); setAssignAccounts(0); setAssignDays(5); }}
                                    className={`cursor-pointer transition-colors ${assignBucket === b.id ? "bg-violet-500/10" : "hover:bg-zinc-200 dark:hover:bg-zinc-800/30"}`}>
                                    <td className="px-3 py-1.5 text-zinc-800 dark:text-zinc-300 font-medium">{b.name}</td>
                                    <td className="px-3 py-1.5 text-right font-mono text-zinc-600 dark:text-zinc-400">{b.total_contacts.toLocaleString()}</td>
                                    <td className="px-3 py-1.5 text-right font-mono text-violet-400">{b.remaining_contacts.toLocaleString()}</td>
                                    <td className="px-3 py-1.5">
                                      <div className="flex gap-1">{b.countries.map((c) => <span key={c} className="px-1 py-0.5 text-[9px] bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 rounded">{c}</span>)}</div>
                                    </td>
                                    <td className="px-3 py-1.5 text-zinc-600 dark:text-zinc-400">{b.emp_range}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}

                  {/* ── Child list rows ─────────────────────────────── */}
                  {w.expanded && w.lists.map((l) => (
                    <tr key={l.id} className={`border-b border-zinc-200 dark:border-zinc-800/20 transition-colors ${
                      l.isNonjoiners || l.isNoListData ? "bg-zinc-50 dark:bg-zinc-900/20 text-zinc-500 italic" :
                      selectedIds.has(l.id) ? "bg-violet-500/5" : "hover:bg-zinc-100 dark:bg-zinc-800/20"
                    }`}>
                      <td className="px-2 py-1.5"></td>
                      <td className="px-1 py-1.5">
                        {!l.isNonjoiners && !l.isNoListData && (
                          <div onClick={() => toggleSelect(l.id)} className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center cursor-pointer transition-colors ${
                            selectedIds.has(l.id) ? "bg-violet-600 border-violet-600" : "border-zinc-600 hover:border-zinc-500"
                          }`}>
                            {selectedIds.has(l.id) && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><path d="M20 6L9 17l-5-5"/></svg>}
                          </div>
                        )}
                      </td>
                      <td className="px-2 py-1.5"></td>
                      <td className="px-2 py-1.5"></td>
                      <td className="px-2 py-1.5">
                        <span className={l.isNonjoiners || l.isNoListData ? "text-zinc-500" : "text-zinc-800 dark:text-zinc-300"}>{l.description}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        {l.bucket !== "—" ? (
                          <span className="text-zinc-600 dark:text-zinc-400 text-[10px] bg-zinc-100 dark:bg-zinc-800/60 px-1.5 py-0.5 rounded border border-zinc-300 dark:border-zinc-700/30 whitespace-nowrap">
                            {l.bucket.length > 25 ? l.bucket.substring(0, 25) + "…" : l.bucket}
                          </span>
                        ) : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-2 py-1.5"><SenderBadge name={l.sender} color={l.senderColor} /></td>
                      <td className="px-2 py-1.5 text-right font-mono text-zinc-800 dark:text-zinc-300">{l.listSize > 0 ? l.listSize.toLocaleString() : ""}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-violet-400">{l.listRemain > 0 ? l.listRemain.toLocaleString() : l.listSize > 0 ? "0" : ""}</td>
                      <td className="px-2 py-1.5">
                        {l.title ? (
                          <div className="max-w-[240px]">
                            <span className="text-zinc-700 dark:text-zinc-300 text-[10px] leading-snug line-clamp-2 block" title={l.title}>{l.title}</span>
                            {l.titleVariants && l.titleVariants.length > 1 && (
                              <button onClick={() => setPlanningCopyModal({ listId: l.id, webinarId: w.id, tab: "title" })}
                                className="text-[9px] text-violet-500 hover:text-violet-400 font-medium mt-0.5 transition-colors">
                                {l.titleVariants.length} variations →
                              </button>
                            )}
                          </div>
                        ) : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-2 py-1.5">
                        {(() => {
                          const selectedDesc = l.descVariants?.find(v => v.selected);
                          const descText = selectedDesc?.text || "";
                          return descText ? (
                            <div className="max-w-[240px]">
                              <span className="text-zinc-700 dark:text-zinc-300 text-[10px] leading-snug line-clamp-2 block" title={descText}>{descText}</span>
                              {l.descVariants && l.descVariants.length > 1 && (
                                <button onClick={() => setPlanningCopyModal({ listId: l.id, webinarId: w.id, tab: "description" })}
                                  className="text-[9px] text-blue-500 hover:text-blue-400 font-medium mt-0.5 transition-colors">
                                  {l.descVariants.length} variations →
                                </button>
                              )}
                            </div>
                          ) : <span className="text-zinc-600">—</span>;
                        })()}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-emerald-400">{l.accountsNeeded > 0 ? l.accountsNeeded : ""}</td>
                      <td className="px-2 py-1.5 text-center">
                        {l.copiesGenerated ? (
                          <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 inline-flex items-center justify-center">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M20 6L9 17l-5-5"/></svg>
                          </span>
                        ) : !l.isNonjoiners && !l.isNoListData ? (
                          <span className="text-zinc-600 text-[10px]">—</span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              );
            })}
        </table>
      </div>

      {/* ── Bulk action bar ─────────────────────────────────────────── */}
      {selectedCount > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-xl shadow-2xl shadow-black/50 px-5 py-3 flex items-center gap-4">
          <span className="text-sm text-zinc-800 dark:text-zinc-300 font-medium">{selectedCount} list{selectedCount > 1 ? "s" : ""} selected</span>
          <div className="w-px h-5 bg-zinc-200 dark:bg-zinc-700" />
          <button onClick={openCopyModal} className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            Generate Copies
          </button>
          <button onClick={() => setSelectedIds(new Set())} className="text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:text-zinc-200 transition-colors">Clear</button>
        </div>
      )}

      {/* ── Copy generation modal ──────────────────────────────────── */}
      {showCopyModal && (
        <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-12 overflow-y-auto">
          <div className="bg-zinc-50 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-2xl shadow-2xl max-w-4xl w-full mx-4 mb-12">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-800/40">
              <div>
                <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Generate Copies</h2>
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5">{copyModalLists.length} list{copyModalLists.length > 1 ? "s" : ""} · title + description variants per bucket</p>
              </div>
              <div className="flex items-center gap-3">
                {!copyModalLists[0]?.copiesGenerated && (
                  <button onClick={handleGenerateCopies} disabled={generatingCopies}
                    className="px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 text-white text-sm font-semibold rounded-lg transition-colors flex items-center gap-2">
                    {generatingCopies ? (
                      <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> Generating...</>
                    ) : (
                      <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> Generate All</>
                    )}
                  </button>
                )}
                <button onClick={closeCopyModal} className="text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:text-zinc-200 transition-colors p-1">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>

            {/* Modal body */}
            <div className="px-6 py-4 max-h-[70vh] overflow-y-auto space-y-6">
              {copyModalLists.map((l) => (
                <div key={l.id} className="rounded-xl border border-zinc-200 dark:border-zinc-800/60 overflow-hidden">
                  {/* List header */}
                  <div className="bg-zinc-100 dark:bg-zinc-800/30 px-4 py-3 flex items-center justify-between">
                    <div>
                      <span className="text-sm text-zinc-800 dark:text-zinc-200 font-medium">{l.description}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-zinc-500 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded border border-zinc-300 dark:border-zinc-700/30">{l.bucket}</span>
                        <SenderBadge name={l.sender} color={l.senderColor} />
                        <span className="text-[10px] text-zinc-500 font-mono">{l.listSize.toLocaleString()} contacts</span>
                      </div>
                    </div>
                    {l.copiesGenerated && <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">Generated</span>}
                  </div>

                  {l.copiesGenerated && l.titleVariants && l.descVariants && (
                    <div className="px-4 py-4 space-y-4">
                      {/* Titles */}
                      <div>
                        <span className="text-[10px] font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider block mb-2">Title Variants</span>
                        <div className="space-y-2">
                          {l.titleVariants.map((v, i) => (
                            <label key={v.id} onClick={() => selectVariant(l.id, "title", v.id)}
                              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                                v.selected ? "border-violet-500/40 bg-violet-500/5" : "border-zinc-200 dark:border-zinc-800/40 hover:border-zinc-300 dark:border-zinc-700/60"
                              }`}>
                              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                                v.selected ? "border-violet-500 bg-violet-500" : "border-zinc-600"
                              }`}>
                                {v.selected && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                              </div>
                              <div>
                                <span className="text-[10px] text-zinc-500 font-semibold uppercase">Variant {String.fromCharCode(65 + i)}</span>
                                <p className="text-sm text-zinc-800 dark:text-zinc-200 mt-0.5 leading-relaxed">{v.text}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Descriptions */}
                      <div>
                        <span className="text-[10px] font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider block mb-2">Description Variants</span>
                        <div className="space-y-2">
                          {l.descVariants.map((v, i) => (
                            <label key={v.id} onClick={() => selectVariant(l.id, "desc", v.id)}
                              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                                v.selected ? "border-violet-500/40 bg-violet-500/5" : "border-zinc-200 dark:border-zinc-800/40 hover:border-zinc-300 dark:border-zinc-700/60"
                              }`}>
                              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                                v.selected ? "border-violet-500 bg-violet-500" : "border-zinc-600"
                              }`}>
                                {v.selected && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                              </div>
                              <div>
                                <span className="text-[10px] text-zinc-500 font-semibold uppercase">Variant {String.fromCharCode(65 + i)}</span>
                                <p className="text-sm text-zinc-800 dark:text-zinc-300 mt-0.5 leading-relaxed">{v.text}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {!l.copiesGenerated && (
                    <div className="px-4 py-8 text-center">
                      <p className="text-sm text-zinc-500">Click &quot;Generate All&quot; to create title and description variants</p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Modal footer */}
            {copyModalLists.some((l) => l.copiesGenerated) && (
              <div className="px-6 py-4 border-t border-zinc-200 dark:border-zinc-800/40 flex justify-end gap-3">
                <button onClick={closeCopyModal} className="px-4 py-2 text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:text-zinc-200 border border-zinc-300 dark:border-zinc-700/60 rounded-lg hover:bg-zinc-100 dark:bg-zinc-800/50 transition-colors">Cancel</button>
                <button onClick={closeCopyModal} className="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold rounded-lg transition-colors">
                  Apply Selected Variants
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Planning Copy Variant Modal ─────────────────────────────── */}
      {planningCopyModal && (() => {
        const targetList = webinars.flatMap(w => w.lists).find(l => l.id === planningCopyModal.listId);
        if (!targetList) return null;
        const variants = planningCopyModal.tab === "title" ? targetList.titleVariants : targetList.descVariants;
        if (!variants || variants.length === 0) return null;
        const isTitle = planningCopyModal.tab === "title";
        return (
          <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center" onClick={(e) => { if (e.target === e.currentTarget) setPlanningCopyModal(null); }}>
            <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/60 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[70vh] flex flex-col overflow-hidden">
              {/* Header */}
              <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-800/40 shrink-0">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                      {isTitle ? "Title" : "Description"} Variations
                    </h3>
                    <p className="text-[10px] text-zinc-500 mt-0.5">
                      {targetList.bucket} · {targetList.sender}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPlanningCopyModal({ ...planningCopyModal, tab: isTitle ? "description" : "title" })}
                      className="text-[10px] text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 px-2 py-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800/50 transition-colors"
                    >
                      Switch to {isTitle ? "Descriptions" : "Titles"}
                    </button>
                    <button onClick={() => setPlanningCopyModal(null)} className="p-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                </div>
              </div>

              {/* Variants */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
                {variants.map((v, i) => (
                  <button
                    key={v.id}
                    onClick={() => {
                      selectVariant(targetList.id, isTitle ? "title" : "desc", v.id);
                    }}
                    className={`w-full text-left p-3 rounded-lg border transition-all flex items-start gap-3 ${
                      v.selected
                        ? isTitle
                          ? "border-violet-400 dark:border-violet-500/40 bg-violet-50/50 dark:bg-violet-500/5"
                          : "border-blue-400 dark:border-blue-500/40 bg-blue-50/50 dark:bg-blue-500/5"
                        : "border-zinc-200 dark:border-zinc-800/40 hover:border-zinc-300 dark:hover:border-zinc-700"
                    }`}
                  >
                    <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                      v.selected
                        ? isTitle ? "border-violet-500 bg-violet-500" : "border-blue-500 bg-blue-500"
                        : "border-zinc-400"
                    }`}>
                      {v.selected && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                    </div>
                    <div>
                      <span className="text-[9px] text-zinc-500 font-semibold uppercase">Variant {i + 1}</span>
                      <p className="text-xs text-zinc-800 dark:text-zinc-200 mt-0.5 leading-relaxed">{v.text}</p>
                    </div>
                  </button>
                ))}
              </div>

              {/* Footer */}
              <div className="px-6 py-3 border-t border-zinc-200 dark:border-zinc-800/40 flex justify-end shrink-0">
                <button onClick={() => setPlanningCopyModal(null)}
                  className="px-5 py-2 bg-zinc-900 dark:bg-zinc-100 hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-semibold rounded-lg transition-colors">
                  Done
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── New Webinar Modal ──────────────────────────────────────── */}
      {showNewWebinarModal && (
        <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center" onClick={(e) => { if (e.target === e.currentTarget) setShowNewWebinarModal(false); }}>
          <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/60 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-800/40 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100">New Webinar</h3>
                <p className="text-[11px] text-zinc-500 mt-0.5">Create a new webinar campaign</p>
              </div>
              <button onClick={() => setShowNewWebinarModal(false)} className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium block mb-1.5">Webinar Number</label>
                <input
                  type="number"
                  value={newWebinarNumber}
                  onChange={(e) => setNewWebinarNumber(parseInt(e.target.value) || 0)}
                  className="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 font-mono focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition-colors"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium block mb-1.5">Webinar Date</label>
                <input
                  type="date"
                  value={newWebinarDate}
                  onChange={(e) => setNewWebinarDate(e.target.value)}
                  className="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition-colors [color-scheme:dark]"
                />
              </div>
              {/* Preview */}
              {newWebinarNumber > 0 && newWebinarDate && (
                <div className="bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700/30 rounded-lg px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-bold text-zinc-900 dark:text-zinc-100">W{newWebinarNumber}</span>
                    <span className="text-zinc-300 dark:text-zinc-600">·</span>
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                      {new Date(newWebinarDate + "T00:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <StatusBadge status="Planning" />
                    <span className="text-[10px] text-zinc-500">0 lists assigned</span>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-zinc-200 dark:border-zinc-800/40 flex items-center justify-between">
              <button onClick={() => setShowNewWebinarModal(false)} className="px-4 py-2 text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 transition-colors">
                Cancel
              </button>
              <button
                onClick={handleCreateWebinar}
                disabled={!newWebinarNumber || !newWebinarDate}
                className="px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-sm font-semibold rounded-lg transition-colors flex items-center gap-1.5"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                Create Webinar
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
