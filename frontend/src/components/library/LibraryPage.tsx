"use client";

import { useState, useEffect, useCallback } from "react";
import { loadLibrary, updateGenerationStatus, deleteGeneration, StoredGeneration, GenerationStatus } from "@/lib/store";

const VARIANT_CONFIG = {
  A: { label: "Curiosity", color: "text-violet-400", dot: "bg-violet-400", activeBg: "bg-violet-500/[0.06]", border: "border-violet-500/20" },
  B: { label: "Outcome",   color: "text-sky-400",    dot: "bg-sky-400",    activeBg: "bg-sky-500/[0.06]",    border: "border-sky-500/20" },
  C: { label: "Mechanism", color: "text-emerald-400", dot: "bg-emerald-400", activeBg: "bg-emerald-500/[0.06]", border: "border-emerald-500/20" },
} as const;

const STATUS_CONFIG = {
  new:          { dot: "bg-zinc-600",   label: "new",        text: "text-zinc-500" },
  saved:        { dot: "bg-emerald-500", label: "saved",      text: "text-emerald-500" },
  "needs-work": { dot: "bg-amber-500",  label: "needs work", text: "text-amber-500" },
} as const;

function CopyBtn({ onClick, copied }: { onClick: () => void; copied: boolean }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1 text-[11px] font-medium px-2 py-[3px] rounded transition-all duration-100 ${
        copied ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-700/40"
      }`}
    >
      {copied
        ? <><svg width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>Copied</>
        : <><svg width="10" height="10" viewBox="0 0 12 12" fill="none"><rect x="4" y="1" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M1 4.5V10a1 1 0 001 1h5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>Copy</>
      }
    </button>
  );
}

function GenerationCard({ gen, onUpdate }: { gen: StoredGeneration; onUpdate: () => void }) {
  const [activeVariant, setActiveVariant] = useState<"A" | "B" | "C">("A");
  const [copied, setCopied] = useState<string | null>(null);

  function copy(key: string, text: string) { navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 2000); }
  function setStatus(s: GenerationStatus) { updateGenerationStatus(gen.id, s); onUpdate(); }

  const variant = gen.variants.find((v) => v.variant === activeVariant);
  const cfg = VARIANT_CONFIG[activeVariant];
  const sc = STATUS_CONFIG[gen.status];
  const date = new Date(gen.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-zinc-800 bg-zinc-950/40">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600 shrink-0">Calendar</span>
        <span className="w-px h-3 bg-zinc-800 shrink-0" />
        <span className="text-sm font-medium text-zinc-200 truncate">{gen.audience}</span>
        <span className="text-zinc-700">·</span>
        <span className="text-xs text-zinc-600 shrink-0">{date}</span>
        <div className="flex-1" />
        <div className={`flex items-center gap-1.5 shrink-0 ${sc.text}`}>
          <span className={`w-[5px] h-[5px] rounded-full ${sc.dot}`} />
          <span className="text-[10px] font-medium">{sc.label}</span>
        </div>
      </div>

      {/* Variant tabs */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800 bg-zinc-950/20">
        {gen.variants.map((v) => {
          const vc = VARIANT_CONFIG[v.variant];
          const isActive = activeVariant === v.variant;
          return (
            <button key={v.variant} onClick={() => setActiveVariant(v.variant)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all duration-100 ${
                isActive ? `${vc.activeBg} ${vc.color} border ${vc.border}` : "text-zinc-600 hover:text-zinc-300"
              }`}
            >
              <span className={`w-[5px] h-[5px] rounded-full ${vc.dot}`} />
              {v.variant}: {vc.label}
            </button>
          );
        })}
      </div>

      {variant && (
        <>
          <div className={`px-5 py-4 border-b border-zinc-800/50 ${cfg.activeBg}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">Title</span>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] ${variant.title.length > 60 ? "text-amber-400/70" : "text-zinc-700"}`}>{variant.title.length} chars{variant.title.length > 60 ? " · may clip" : ""}</span>
                <CopyBtn onClick={() => copy("title", variant.title)} copied={copied === "title"} />
              </div>
            </div>
            <p className="text-zinc-100 text-[15px] font-semibold leading-snug">{variant.title}</p>
          </div>

          <div className={`px-5 py-4 border-b border-zinc-800/50 ${cfg.activeBg}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">Description</span>
              <CopyBtn onClick={() => copy("desc", variant.description)} copied={copied === "desc"} />
            </div>
            <pre className="text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap font-sans">{variant.description}</pre>
          </div>
        </>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 px-5 py-3 bg-zinc-950/40 border-t border-zinc-800">
        <button onClick={() => setStatus("saved")}
          className={`flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-md border transition-all duration-100 ${
            gen.status === "saved" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" : "border-zinc-700/60 text-zinc-500 hover:border-emerald-500/25 hover:text-emerald-400"
          }`}
        >
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          Save
        </button>
        <button onClick={() => setStatus("needs-work")}
          className={`flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-md border transition-all duration-100 ${
            gen.status === "needs-work" ? "border-amber-500/30 bg-amber-500/10 text-amber-400" : "border-zinc-700/60 text-zinc-500 hover:border-amber-500/25 hover:text-amber-400"
          }`}
        >
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.2"/><path d="M6 4v2M6 7.5h.01" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
          Needs work
        </button>
        <div className="flex-1" />
        {variant && <CopyBtn onClick={() => copy("all", `TITLE: ${variant.title}\n\nDESCRIPTION:\n${variant.description}`)} copied={copied === "all"} />}
        <button onClick={() => { deleteGeneration(gen.id); onUpdate(); }}
          className="flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-md border border-zinc-700/60 text-zinc-600 hover:border-red-500/25 hover:text-red-400 transition-all duration-100"
        >
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 3h8M5 3V2h2v1M3 3l.5 7h5L9 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          Purge
        </button>
      </div>
    </div>
  );
}

type StatusFilter = GenerationStatus | "all";

export function LibraryPage() {
  const [items, setItems] = useState<StoredGeneration[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const reload = useCallback(() => setItems(loadLibrary()), []);
  useEffect(() => { reload(); }, [reload]);

  const filtered = items.filter((g) =>
    (!search || g.audience.toLowerCase().includes(search.toLowerCase())) &&
    (statusFilter === "all" || g.status === statusFilter)
  );

  return (
    <div className="min-h-[calc(100vh-48px)] bg-zinc-950">
      <div className="max-w-3xl mx-auto px-6 py-12 space-y-8">

        <div>
          <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Library</h1>
          <p className="text-sm text-zinc-500 mt-1.5">All generated content, ready to review and copy.</p>
        </div>

        {items.length > 0 && (
          <div className="flex items-center gap-2.5">
            <div className="relative flex-1">
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none" className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none">
                <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                <path d="M10 10l2 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
              <input type="text" placeholder="Search audience..." value={search} onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-8 pr-4 py-2 text-sm text-zinc-100 placeholder:text-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-600 focus:border-zinc-600 transition-colors"
              />
            </div>
            <div className="flex items-center gap-px p-[3px] bg-zinc-900 border border-zinc-800 rounded-lg">
              {(["all", "new", "saved", "needs-work"] as const).map((s) => (
                <button key={s} onClick={() => setStatusFilter(s)}
                  className={`text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-100 whitespace-nowrap ${
                    statusFilter === s ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >{s === "needs-work" ? "Needs work" : s.charAt(0).toUpperCase() + s.slice(1)}</button>
              ))}
            </div>
          </div>
        )}

        {filtered.length > 0 ? (
          <>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-700">
              {filtered.length} of {items.length} generation{items.length !== 1 ? "s" : ""}
            </p>
            <div className="space-y-3">
              {filtered.map((gen) => <GenerationCard key={gen.id} gen={gen} onUpdate={reload} />)}
            </div>
          </>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <div className="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="3" y="2" width="12" height="14" rx="2" stroke="#3f3f46" strokeWidth="1.3"/>
                <path d="M6 6h6M6 9h6M6 12h4" stroke="#3f3f46" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <p className="text-sm text-zinc-400">No content yet.</p>
              <a href="/" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors underline underline-offset-2 mt-0.5 block">
                Go to Studio to generate your first batch
              </a>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-1.5 text-center">
            <p className="text-sm text-zinc-500">No results.</p>
            <button onClick={() => { setSearch(""); setStatusFilter("all"); }} className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">Clear filters</button>
          </div>
        )}
      </div>
    </div>
  );
}
