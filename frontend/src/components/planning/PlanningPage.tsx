"use client";

import { useState, useMemo, useCallback } from "react";

/* ─── Types ────────────────────────────────────────────────────────────── */

interface AvailableBucket {
  id: string;
  name: string;
  totalContacts: number;
  remaining: number;
  countries: string[];
  empRange: string;
  industry: string;
}

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
  sendsPerDay: number;
  daysPerWeek: number;
  color: string;
}

/* ─── Sender + Badge Helpers ───────────────────────────────────────────── */

const SENDERS: Sender[] = [
  { id: "santi", name: "Santi", sendsPerDay: 500, daysPerWeek: 5, color: "violet" },
  { id: "skarpe", name: "Skarpe", sendsPerDay: 400, daysPerWeek: 5, color: "blue" },
  { id: "lina", name: "Lina", sendsPerDay: 300, daysPerWeek: 5, color: "emerald" },
];

const SENDER_COLORS: Record<string, string> = {
  santi: "bg-violet-500/15 text-violet-400 border-violet-500/25",
  skarpe: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  lina: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
};

function SenderBadge({ name }: { name: string }) {
  if (!name) return <span className="text-zinc-600">—</span>;
  const key = name.toLowerCase().split(" ")[0];
  const cls = SENDER_COLORS[key] || "bg-zinc-700/30 text-zinc-400 border-zinc-600/30";
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
  const cls = colors[key] || "bg-zinc-700/30 text-zinc-400 border-zinc-600/30";
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>{variant}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { badge: string; dot: string }> = {
    planning: { badge: "bg-amber-500/10 text-amber-400 border-amber-500/20", dot: "bg-amber-400" },
    sent: { badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", dot: "bg-emerald-400" },
  };
  const c = colors[status.toLowerCase()] || { badge: "bg-zinc-700/30 text-zinc-400 border-zinc-600/30", dot: "bg-zinc-400" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {status}
    </span>
  );
}

/* ─── Mock Data ────────────────────────────────────────────────────────── */

const INITIAL_BUCKETS: AvailableBucket[] = [
  { id: "b1", name: "Accounting, Audit & Tax Services", totalContacts: 38400, remaining: 32100, countries: ["US", "UK", "CA"], empRange: "5-50", industry: "Accounting" },
  { id: "b2", name: "Financial Planning & Advisory", totalContacts: 22100, remaining: 19800, countries: ["US", "AU"], empRange: "5-50", industry: "Financial Planning" },
  { id: "b3", name: "Insurance Brokerage", totalContacts: 8900, remaining: 7200, countries: ["US"], empRange: "5-50", industry: "Insurance" },
  { id: "b4", name: "Professional Training & Coaching", totalContacts: 15200, remaining: 13400, countries: ["US"], empRange: "0-10", industry: "Pro Training" },
  { id: "b5", name: "Wealth Management", totalContacts: 11200, remaining: 9400, countries: ["US", "UK"], empRange: "10-50", industry: "Wealth Mgmt" },
  { id: "b6", name: "Real Estate Services", totalContacts: 6300, remaining: 5100, countries: ["US"], empRange: "5-50", industry: "Real Estate" },
  { id: "b7", name: "Legal Services", totalContacts: 4200, remaining: 3800, countries: ["US", "UK", "CA"], empRange: "5-25", industry: "Legal" },
  { id: "b8", name: "Business Consulting", totalContacts: 3100, remaining: 2900, countries: ["US"], empRange: "1-25", industry: "Consulting" },
  { id: "b9", name: "IT Services & MSP", totalContacts: 2400, remaining: 2100, countries: ["US", "IN"], empRange: "5-50", industry: "IT Services" },
  { id: "b10", name: "Marketing & Advertising Agency", totalContacts: 2200, remaining: 1900, countries: ["US", "UK"], empRange: "1-25", industry: "Marketing" },
];

function createPastWebinarLists(webNum: number): PlannedList[] {
  const lists: Record<number, PlannedList[]> = {
    134: [
      { id: "134-1", webinarId: "w134", description: "Pt 2a. Ampleleads, Feb 25, Pro Training & Coaching, 5-1, US", listUrl: "https://rowzero.co", bucket: "Professional Training & Coaching", sender: "Santi", dateSend: "Apr 7", listSize: 40000, listRemain: 29688, gcalInvited: 0, descVariant: "C&A v4", title: "Revealed: How Consultants Are Using AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Pro Training", empRange: "5-10", country: "US", copiesGenerated: true, titleVariants: [{ id: "t1", text: "Revealed: How Consultants Are Using AI Powered Webinars to Build Predictable Pipeline In 2026", selected: true }, { id: "t2", text: "The Secret System 200+ Consulting Firms Use to Book 10x More Calls", selected: false }, { id: "t3", text: "Webinar: Why Top Consultants Are Ditching Cold Outreach in 2026", selected: false }], descVariants: [{ id: "d1", text: "Join us live to see the exact AI-powered system that professional service firms are using to fill their pipeline with qualified leads — without cold calling.", selected: true }, { id: "d2", text: "In 45 minutes, you'll discover the 3-step framework that turned a stagnant consulting practice into a $50K/month lead machine.", selected: false }, { id: "d3", text: "See the live demo of the calendar-based outreach system that's generating 10+ booked calls per week for B2B consultants.", selected: false }] },
      { id: "134-2", webinarId: "w134", description: "Pt 2b. Ampleleads, Feb 25, Pro Training & Coaching, 5-1, US", listUrl: "https://rowzero.co", bucket: "Professional Training & Coaching", sender: "Skarpe", dateSend: "Apr 7", listSize: 40000, listRemain: 39978, gcalInvited: 0, descVariant: "C&A v4", title: "Revealed: How Consultants Are Using AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 67, industry: "Pro Training", empRange: "5-10", country: "US", copiesGenerated: true },
      { id: "134-3", webinarId: "w134", description: "Pt 2a. Ampleleads, Mar 11, Insurance, 5-10, US", listUrl: "https://rowzero.co", bucket: "Insurance Brokerage", sender: "Santi", dateSend: "Apr 7", listSize: 20500, listRemain: 19420, gcalInvited: 0, descVariant: "Fin v3", title: "Revealed: How Finance & Insurance Firms Use AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Insurance", empRange: "5-10", country: "US", copiesGenerated: true },
      { id: "134-4", webinarId: "w134", description: "Pt 2b. Ampleleads, Mar 11, Insurance, 5-10, US", listUrl: "https://rowzero.co", bucket: "Insurance Brokerage", sender: "Skarpe", dateSend: "Apr 7", listSize: 20500, listRemain: 19280, gcalInvited: 0, descVariant: "Fin v3", title: "Revealed: How Finance & Insurance Firms Use AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 34.2, industry: "Insurance", empRange: "5-10", country: "US", copiesGenerated: true },
      { id: "134-5", webinarId: "w134", description: "Pt 1a. Ampleleads, Mar 11, Insurance, 10-25, US", listUrl: "https://rowzero.co", bucket: "Insurance Brokerage", sender: "Santi", dateSend: "Apr 7", listSize: 22000, listRemain: 20335, gcalInvited: 0, descVariant: "Fin James", title: "Revealed: How Finance & Insurance Firms Use AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Insurance", empRange: "10-25", country: "US", copiesGenerated: true },
      { id: "134-nj", webinarId: "w134", description: "Nonjoiners", listUrl: "", bucket: "—", sender: "", dateSend: "", listSize: 0, listRemain: 0, gcalInvited: 0, descVariant: "", title: "", accountsNeeded: 0, industry: "", empRange: "", country: "", isNonjoiners: true },
      { id: "134-nld", webinarId: "w134", description: "NO LIST DATA", listUrl: "", bucket: "—", sender: "", dateSend: "", listSize: 0, listRemain: 2723, gcalInvited: 0, descVariant: "", title: "", accountsNeeded: 0, industry: "", empRange: "", country: "", isNoListData: true },
    ],
    133: [
      { id: "133-1", webinarId: "w133", description: "Pt 2a. Ampleleads, Feb 25, Consulting & Adv, 0-5, US", listUrl: "https://rowzero.co", bucket: "Business Consulting", sender: "Santi", dateSend: "Mar 31", listSize: 30000, listRemain: 21345, gcalInvited: 0, descVariant: "C&A v4", title: "Revealed: How Consultants Are Using AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Consulting", empRange: "0-5", country: "US", copiesGenerated: true },
      { id: "133-2", webinarId: "w133", description: "Pt 2b. Ampleleads, Feb 25, Consulting & Adv, 0-5, US", listUrl: "https://rowzero.co", bucket: "Business Consulting", sender: "Skarpe", dateSend: "Mar 31", listSize: 30000, listRemain: 23894, gcalInvited: 0, descVariant: "C&A v4", title: "Revealed: How Consultants Are Using AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Consulting", empRange: "0-5", country: "US", copiesGenerated: true },
      { id: "133-3", webinarId: "w133", description: "Pt 1a. Ampleleads, Mar 11, Insurance, 0-5, US", listUrl: "https://rowzero.co", bucket: "Insurance Brokerage", sender: "Santi", dateSend: "Mar 31", listSize: 12500, listRemain: 12471, gcalInvited: 0, descVariant: "Fin James", title: "Revealed: How Finance & Insurance Firms Use AI Powered Webinars to Build Predictable Pipeline In 2026", accountsNeeded: 0, industry: "Insurance", empRange: "0-5", country: "US", copiesGenerated: true },
      { id: "133-nj", webinarId: "w133", description: "Nonjoiners", listUrl: "", bucket: "—", sender: "", dateSend: "", listSize: 0, listRemain: 0, gcalInvited: 0, descVariant: "", title: "", accountsNeeded: 0, industry: "", empRange: "", country: "", isNonjoiners: true },
      { id: "133-nld", webinarId: "w133", description: "NO LIST DATA", listUrl: "", bucket: "—", sender: "", dateSend: "", listSize: 0, listRemain: 134, gcalInvited: 0, descVariant: "", title: "", accountsNeeded: 0, industry: "", empRange: "", country: "", isNoListData: true },
    ],
  };
  return lists[webNum] || [];
}

/* ─── Copy generation ──────────────────────────────────────────────────── */

function generateMockCopies(bucket: string, industry: string) {
  const titleTemplates: Record<string, string[]> = {
    default: [
      `Revealed: How ${industry} Firms Use AI Powered Webinars to Build Predictable Pipeline In 2026`,
      `The Secret System 200+ ${industry} Firms Use to Book 10x More Qualified Calls`,
      `Webinar: Why Top ${industry} Professionals Are Ditching Cold Outreach in 2026`,
    ],
  };
  const descTemplates = [
    `Join us live to see the exact AI-powered system that ${industry.toLowerCase()} firms are using to fill their pipeline with qualified leads — without cold calling or referrals.`,
    `In 45 minutes, you'll discover the 3-step framework that turned a stagnant ${industry.toLowerCase()} practice into a $50K/month lead generation machine. Real case studies included.`,
    `See the live demo of the calendar-based outreach system that's generating 10+ booked calls per week for B2B ${industry.toLowerCase()} professionals. Limited spots.`,
  ];
  const titles = (titleTemplates[bucket.toLowerCase()] || titleTemplates.default).map((t, i) => ({
    id: `t${i}`, text: t, selected: i === 0,
  }));
  const descs = descTemplates.map((d, i) => ({
    id: `d${i}`, text: d, selected: i === 0,
  }));
  return { titles, descs };
}

/* ─── Main Component ───────────────────────────────────────────────────── */

export function PlanningPage() {
  const [buckets, setBuckets] = useState<AvailableBucket[]>(INITIAL_BUCKETS);
  const [webinars, setWebinars] = useState<Webinar[]>([
    { id: "w135", number: 135, date: "April 14, 2026", status: "Planning", broadcastId: "—", mainTitle: "", lists: [], expanded: true, showAssignment: true },
    { id: "w134", number: 134, date: "April 7, 2026", status: "Sent", broadcastId: "6047654", mainTitle: "TITLE: Revealed: How Professional Service Firms Using AI Powered Webinars...", lists: createPastWebinarLists(134), expanded: false, showAssignment: false },
    { id: "w133", number: 133, date: "March 31, 2026", status: "Sent", broadcastId: "6012344", mainTitle: "TITLE: Revealed: How Professional Service Firms Using AI Powered Webinars...", lists: createPastWebinarLists(133), expanded: false, showAssignment: false },
  ]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copyModalLists, setCopyModalLists] = useState<PlannedList[]>([]);
  const [generatingCopies, setGeneratingCopies] = useState(false);

  // Assignment form state
  const [assignBucket, setAssignBucket] = useState("");
  const [assignSender, setAssignSender] = useState("");
  const [assignVolume, setAssignVolume] = useState(0);
  const [assignWebinar, setAssignWebinar] = useState("w135");

  /* ── Stats ─────────────────────────────────────────────────────────── */

  const globalStats = useMemo(() => {
    const allLists = webinars.flatMap((w) => w.lists.filter((l) => !l.isNonjoiners && !l.isNoListData));
    return {
      totalLists: allLists.length,
      totalVolume: allLists.reduce((s, l) => s + l.listSize, 0),
      totalRemaining: allLists.reduce((s, l) => s + l.listRemain, 0),
      totalAccounts: Math.round(allLists.reduce((s, l) => s + l.accountsNeeded, 0)),
      availableBuckets: buckets.reduce((s, b) => s + b.remaining, 0),
    };
  }, [webinars, buckets]);

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

  const handleAssign = useCallback(() => {
    if (!assignBucket || !assignSender || assignVolume <= 0) return;
    const bucket = buckets.find((b) => b.id === assignBucket);
    const sender = SENDERS.find((s) => s.id === assignSender);
    if (!bucket || !sender) return;

    const volume = Math.min(assignVolume, bucket.remaining);
    const weeklyCapacity = sender.sendsPerDay * sender.daysPerWeek;
    const accounts = Math.ceil(volume / weeklyCapacity);

    const newList: PlannedList = {
      id: `${assignWebinar}-${Date.now()}`,
      webinarId: assignWebinar,
      bucket: bucket.name,
      description: `${bucket.name}, ${bucket.empRange} emp, ${bucket.countries.join("/")}`,
      listUrl: "",
      sender: sender.name,
      dateSend: "",
      listSize: volume,
      listRemain: volume,
      gcalInvited: 0,
      descVariant: "",
      title: "",
      accountsNeeded: accounts,
      industry: bucket.industry,
      empRange: bucket.empRange,
      country: bucket.countries.join(", "),
    };

    // Add to webinar
    setWebinars((prev) => prev.map((w) =>
      w.id === assignWebinar ? { ...w, lists: [...w.lists, newList] } : w
    ));

    // Reduce bucket
    setBuckets((prev) => prev.map((b) =>
      b.id === assignBucket ? { ...b, remaining: b.remaining - volume } : b
    ));

    // Reset
    setAssignBucket("");
    setAssignSender("");
    setAssignVolume(0);
  }, [assignBucket, assignSender, assignVolume, assignWebinar, buckets]);

  const openCopyModal = () => {
    const lists = webinars.flatMap((w) => w.lists).filter((l) => selectedIds.has(l.id) && !l.isNonjoiners && !l.isNoListData);
    setCopyModalLists(lists);
    setShowCopyModal(true);
  };

  const handleGenerateCopies = () => {
    setGeneratingCopies(true);
    setTimeout(() => {
      setWebinars((prev) => prev.map((w) => ({
        ...w,
        lists: w.lists.map((l) => {
          if (!selectedIds.has(l.id)) return l;
          const { titles, descs } = generateMockCopies(l.bucket, l.industry);
          return { ...l, titleVariants: titles, descVariants: descs, copiesGenerated: true };
        }),
      })));
      setGeneratingCopies(false);
      // Update modal lists with generated copies
      setCopyModalLists((prev) => prev.map((l) => {
        const { titles, descs } = generateMockCopies(l.bucket, l.industry);
        return { ...l, titleVariants: titles, descVariants: descs, copiesGenerated: true };
      }));
    }, 1500);
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
      <div className="sticky top-12 z-40 bg-zinc-950/90 backdrop-blur-md border-b border-zinc-800/40 px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-bold text-zinc-100 tracking-tight">Campaign Planning</h1>
            <div className="flex gap-2">
              {[
                { label: "Lists", value: globalStats.totalLists, color: "text-zinc-200" },
                { label: "Volume", value: globalStats.totalVolume.toLocaleString(), color: "text-violet-400" },
                { label: "Available", value: globalStats.availableBuckets.toLocaleString(), color: "text-amber-400" },
                { label: "Accounts", value: globalStats.totalAccounts, color: "text-emerald-400" },
              ].map((s) => (
                <div key={s.label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-900/60 border border-zinc-800/40">
                  <span className={`text-sm font-bold font-mono ${s.color}`}>{s.value}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{s.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search lists, buckets, senders..." className="w-56 bg-zinc-900 border border-zinc-700/60 rounded-lg px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500" />
            <button className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
              New Webinar
            </button>
          </div>
        </div>
      </div>

      {/* Sender legend */}
      <div className="px-6 py-2 flex items-center gap-4 border-b border-zinc-800/20 bg-zinc-950/50">
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Senders:</span>
        {SENDERS.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5">
            <SenderBadge name={s.name} />
            <span className="text-[10px] text-zinc-500 font-mono">{s.sendsPerDay}/d · {s.daysPerWeek}d/w</span>
          </div>
        ))}
      </div>

      {/* ── Webinar table ──────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[1600px]">
          <thead className="sticky top-[108px] z-30">
            <tr className="bg-zinc-900/90 backdrop-blur-sm border-b border-zinc-800/40">
              <th className="w-8 px-2 py-2"></th>
              <th className="w-8 px-1 py-2"></th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Webinar #</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Status</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[320px]">Description of List</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Bucket</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Sender</th>
              <th className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">List Size</th>
              <th className="text-right px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Remaining</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px]">Desc</th>
              <th className="text-left px-2 py-2 text-zinc-500 font-semibold uppercase tracking-wider text-[10px] min-w-[300px]">Title</th>
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
                  <tr className="bg-zinc-800/40 hover:bg-zinc-800/60 cursor-pointer border-t-2 border-zinc-700/40 transition-colors">
                    <td className="px-2 py-2.5 text-center" onClick={() => toggleWebinar(w.id)}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                        className={`text-zinc-400 transition-transform duration-200 ${w.expanded ? "rotate-90" : ""}`}>
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
                      <span className="text-zinc-100 font-bold text-sm">{w.number}</span>
                      <span className="text-zinc-500 ml-2">{w.date}</span>
                    </td>
                    <td className="px-2 py-2.5"><StatusBadge status={w.status} /></td>
                    <td className="px-2 py-2.5" colSpan={3} onClick={() => toggleWebinar(w.id)}>
                      <span className="text-zinc-300 font-medium text-[11px]">{w.mainTitle || `${wLists.length} lists assigned`}</span>
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-zinc-200 font-bold">{wTotal > 0 ? wTotal.toLocaleString() : ""}</td>
                    <td className="px-2 py-2.5 text-right font-mono text-violet-400 font-bold">{wRemain > 0 ? wRemain.toLocaleString() : ""}</td>
                    <td className="px-2 py-2.5"></td>
                    <td className="px-2 py-2.5"></td>
                    <td className="px-2 py-2.5 text-right font-mono text-emerald-400 font-bold">{wAccounts > 0 ? wAccounts : ""}</td>
                    <td className="px-2 py-2.5"></td>
                  </tr>

                  {/* ── Assignment section (for Planning webinars) ──── */}
                  {w.expanded && w.showAssignment && (
                    <tr>
                      <td colSpan={13} className="p-0">
                        <div className="bg-zinc-900/40 border-y border-zinc-800/30 px-6 py-4">
                          <div className="flex items-center justify-between mb-3">
                            <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Assign Buckets to W{w.number}</span>
                            <span className="text-[10px] text-zinc-500">{buckets.filter((b) => b.remaining > 0).length} buckets available · {buckets.reduce((s, b) => s + b.remaining, 0).toLocaleString()} contacts</span>
                          </div>

                          {/* Assignment form */}
                          <div className="flex items-end gap-3 mb-4">
                            <div className="flex-1 min-w-[200px]">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Bucket</label>
                              <select value={assignBucket} onChange={(e) => {
                                setAssignBucket(e.target.value);
                                const b = buckets.find((b) => b.id === e.target.value);
                                if (b) setAssignVolume(b.remaining);
                              }} className="w-full bg-zinc-800 border border-zinc-700/60 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500">
                                <option value="">Select bucket...</option>
                                {buckets.filter((b) => b.remaining > 0).map((b) => (
                                  <option key={b.id} value={b.id}>{b.name} ({b.remaining.toLocaleString()} remaining)</option>
                                ))}
                              </select>
                            </div>
                            <div className="w-36">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Sender</label>
                              <select value={assignSender} onChange={(e) => setAssignSender(e.target.value)} className="w-full bg-zinc-800 border border-zinc-700/60 rounded-md px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-violet-500">
                                <option value="">Select...</option>
                                {SENDERS.map((s) => (
                                  <option key={s.id} value={s.id}>{s.name} ({s.sendsPerDay}/d)</option>
                                ))}
                              </select>
                            </div>
                            <div className="w-36">
                              <label className="text-[10px] text-zinc-500 uppercase tracking-wider block mb-1">Volume</label>
                              <input type="number" value={assignVolume || ""} onChange={(e) => setAssignVolume(parseInt(e.target.value) || 0)} className="w-full bg-zinc-800 border border-zinc-700/60 rounded-md px-3 py-1.5 text-sm text-zinc-200 font-mono focus:outline-none focus:ring-1 focus:ring-violet-500" />
                            </div>
                            <button onClick={handleAssign} disabled={!assignBucket || !assignSender || assignVolume <= 0}
                              className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-xs font-semibold rounded-lg transition-colors whitespace-nowrap">
                              Assign →
                            </button>
                          </div>

                          {/* Available buckets mini-table */}
                          <div className="rounded-lg border border-zinc-800/40 overflow-hidden max-h-[200px] overflow-y-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="bg-zinc-800/40">
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Bucket</th>
                                  <th className="text-right px-3 py-1.5 text-zinc-500 font-medium">Total</th>
                                  <th className="text-right px-3 py-1.5 text-zinc-500 font-medium">Remaining</th>
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Countries</th>
                                  <th className="text-left px-3 py-1.5 text-zinc-500 font-medium">Emp Range</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-zinc-800/20">
                                {buckets.filter((b) => b.remaining > 0).map((b) => (
                                  <tr key={b.id} onClick={() => { setAssignBucket(b.id); setAssignVolume(b.remaining); }}
                                    className={`cursor-pointer transition-colors ${assignBucket === b.id ? "bg-violet-500/10" : "hover:bg-zinc-800/30"}`}>
                                    <td className="px-3 py-1.5 text-zinc-300 font-medium">{b.name}</td>
                                    <td className="px-3 py-1.5 text-right font-mono text-zinc-400">{b.totalContacts.toLocaleString()}</td>
                                    <td className="px-3 py-1.5 text-right font-mono text-violet-400">{b.remaining.toLocaleString()}</td>
                                    <td className="px-3 py-1.5">
                                      <div className="flex gap-1">{b.countries.map((c) => <span key={c} className="px-1 py-0.5 text-[9px] bg-zinc-800 text-zinc-400 rounded">{c}</span>)}</div>
                                    </td>
                                    <td className="px-3 py-1.5 text-zinc-400">{b.empRange}</td>
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
                    <tr key={l.id} className={`border-b border-zinc-800/20 transition-colors ${
                      l.isNonjoiners || l.isNoListData ? "bg-zinc-900/20 text-zinc-500 italic" :
                      selectedIds.has(l.id) ? "bg-violet-500/5" : "hover:bg-zinc-800/20"
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
                        <span className={l.isNonjoiners || l.isNoListData ? "text-zinc-500" : "text-zinc-300"}>{l.description}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        {l.bucket !== "—" ? (
                          <span className="text-zinc-400 text-[10px] bg-zinc-800/60 px-1.5 py-0.5 rounded border border-zinc-700/30 whitespace-nowrap">
                            {l.bucket.length > 25 ? l.bucket.substring(0, 25) + "…" : l.bucket}
                          </span>
                        ) : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-2 py-1.5"><SenderBadge name={l.sender} /></td>
                      <td className="px-2 py-1.5 text-right font-mono text-zinc-300">{l.listSize > 0 ? l.listSize.toLocaleString() : ""}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-violet-400">{l.listRemain > 0 ? l.listRemain.toLocaleString() : l.listSize > 0 ? "0" : ""}</td>
                      <td className="px-2 py-1.5"><VariantBadge variant={l.descVariant} /></td>
                      <td className="px-2 py-1.5">
                        <span className="text-zinc-400 text-[10px] truncate block max-w-[280px]" title={l.title}>{l.title || "—"}</span>
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
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-zinc-900 border border-zinc-700/60 rounded-xl shadow-2xl shadow-black/50 px-5 py-3 flex items-center gap-4">
          <span className="text-sm text-zinc-300 font-medium">{selectedCount} list{selectedCount > 1 ? "s" : ""} selected</span>
          <div className="w-px h-5 bg-zinc-700" />
          <button onClick={openCopyModal} className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            Generate Copies
          </button>
          <button onClick={() => setSelectedIds(new Set())} className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors">Clear</button>
        </div>
      )}

      {/* ── Copy generation modal ──────────────────────────────────── */}
      {showCopyModal && (
        <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-12 overflow-y-auto">
          <div className="bg-zinc-900 border border-zinc-700/60 rounded-2xl shadow-2xl max-w-4xl w-full mx-4 mb-12">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/40">
              <div>
                <h2 className="text-lg font-bold text-zinc-100">Generate Copies</h2>
                <p className="text-xs text-zinc-400 mt-0.5">{copyModalLists.length} list{copyModalLists.length > 1 ? "s" : ""} · 3 title variants + 3 description variants each</p>
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
                <button onClick={closeCopyModal} className="text-zinc-400 hover:text-zinc-200 transition-colors p-1">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>

            {/* Modal body */}
            <div className="px-6 py-4 max-h-[70vh] overflow-y-auto space-y-6">
              {copyModalLists.map((l) => (
                <div key={l.id} className="rounded-xl border border-zinc-800/60 overflow-hidden">
                  {/* List header */}
                  <div className="bg-zinc-800/30 px-4 py-3 flex items-center justify-between">
                    <div>
                      <span className="text-sm text-zinc-200 font-medium">{l.description}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded border border-zinc-700/30">{l.bucket}</span>
                        <SenderBadge name={l.sender} />
                        <span className="text-[10px] text-zinc-500 font-mono">{l.listSize.toLocaleString()} contacts</span>
                      </div>
                    </div>
                    {l.copiesGenerated && <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">Generated</span>}
                  </div>

                  {l.copiesGenerated && l.titleVariants && l.descVariants && (
                    <div className="px-4 py-4 space-y-4">
                      {/* Titles */}
                      <div>
                        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider block mb-2">Title Variants</span>
                        <div className="space-y-2">
                          {l.titleVariants.map((v, i) => (
                            <label key={v.id} onClick={() => selectVariant(l.id, "title", v.id)}
                              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                                v.selected ? "border-violet-500/40 bg-violet-500/5" : "border-zinc-800/40 hover:border-zinc-700/60"
                              }`}>
                              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                                v.selected ? "border-violet-500 bg-violet-500" : "border-zinc-600"
                              }`}>
                                {v.selected && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                              </div>
                              <div>
                                <span className="text-[10px] text-zinc-500 font-semibold uppercase">Variant {String.fromCharCode(65 + i)}</span>
                                <p className="text-sm text-zinc-200 mt-0.5 leading-relaxed">{v.text}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Descriptions */}
                      <div>
                        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider block mb-2">Description Variants</span>
                        <div className="space-y-2">
                          {l.descVariants.map((v, i) => (
                            <label key={v.id} onClick={() => selectVariant(l.id, "desc", v.id)}
                              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                                v.selected ? "border-violet-500/40 bg-violet-500/5" : "border-zinc-800/40 hover:border-zinc-700/60"
                              }`}>
                              <div className={`w-4 h-4 mt-0.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                                v.selected ? "border-violet-500 bg-violet-500" : "border-zinc-600"
                              }`}>
                                {v.selected && <div className="w-1.5 h-1.5 bg-white rounded-full" />}
                              </div>
                              <div>
                                <span className="text-[10px] text-zinc-500 font-semibold uppercase">Variant {String.fromCharCode(65 + i)}</span>
                                <p className="text-sm text-zinc-300 mt-0.5 leading-relaxed">{v.text}</p>
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
              <div className="px-6 py-4 border-t border-zinc-800/40 flex justify-end gap-3">
                <button onClick={closeCopyModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-700/60 rounded-lg hover:bg-zinc-800/50 transition-colors">Cancel</button>
                <button onClick={closeCopyModal} className="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold rounded-lg transition-colors">
                  Apply Selected Variants
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
