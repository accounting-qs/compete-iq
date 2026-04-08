"use client";

import { useState, useEffect, useRef } from "react";
import { Textarea } from "@/components/ui/textarea";
import {
  generateCalendarBlocker,
  CalendarVariant,
} from "@/lib/api";

const AUDIENCE_PRESETS = [
  "Fractional CFOs",
  "Fee-only RIAs",
  "B2B SaaS founders",
  "Agency owners",
  "Independent consultants",
  "Accounting firm owners",
  "Executive coaches",
  "Business exit advisors",
];

const VARIANT_CONFIG = {
  A: { label: "Curiosity", color: "text-violet-400", bg: "bg-violet-500/8", border: "border-violet-500/20", dot: "bg-violet-400" },
  B: { label: "Outcome", color: "text-sky-400", bg: "bg-sky-500/8", border: "border-sky-500/20", dot: "bg-sky-400" },
  C: { label: "Mechanism", color: "text-emerald-400", bg: "bg-emerald-500/8", border: "border-emerald-500/20", dot: "bg-emerald-400" },
} as const;

function CopyButton({ onClick, copied }: { onClick: () => void; copied: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md border transition-all duration-150 ${
        copied
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
          : "border-zinc-700 bg-zinc-800/60 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 hover:bg-zinc-800"
      }`}
    >
      {copied ? (
        <>
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <rect x="4" y="1" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M1 4.5V10a1 1 0 001 1h5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
          Copy
        </>
      )}
    </button>
  );
}

export function CalendarStudio() {
  const [audience, setAudience] = useState("");
  const [clientStory, setClientStory] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [variants, setVariants] = useState<CalendarVariant[]>([]);
  const [copied, setCopied] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  async function handleGenerate() {
    if (!audience.trim()) return;
    setLoading(true);
    setError(null);
    setVariants([]);
    try {
      const result = await generateCalendarBlocker({
        segment: audience.trim(),
        client_story: clientStory.trim() || undefined,
      });
      setVariants(result.variants ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function copy(key: string, text: string) {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  }

  function copyFull(v: CalendarVariant) {
    copy(`${v.variant}-full`, `TITLE: ${v.title}\n\nDESCRIPTION:\n${v.description}`);
  }

  return (
    <div className="min-h-[calc(100vh-57px)] bg-zinc-950">
      <div className="max-w-4xl mx-auto px-6 py-12 space-y-10">

        {/* Page header */}
        <div className="space-y-1">
          <h1 className="text-xl font-semibold text-zinc-100 tracking-tight">Calendar Blockers</h1>
          <p className="text-sm text-zinc-500">Generate 3 variants — curiosity, outcome, and mechanism — ready to paste into any calendar invite.</p>
        </div>

        {/* Input panel */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">

          {/* Audience row */}
          <div className="p-6 space-y-3 border-b border-zinc-800">
            <div className="flex items-baseline justify-between">
              <label className="text-sm font-medium text-zinc-200">Audience</label>
              <span className="text-xs text-zinc-600">Required</span>
            </div>
            <input
              className="w-full bg-zinc-950 border border-zinc-700/80 rounded-lg px-4 py-3 text-zinc-100 text-sm placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 focus:border-zinc-500 transition-colors"
              placeholder="e.g. Fractional CFOs, fee-only RIAs, B2B SaaS founders..."
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
              autoFocus
            />
            <div className="flex flex-wrap gap-2 pt-0.5">
              {AUDIENCE_PRESETS.map((p) => (
                <button
                  key={p}
                  onClick={() => setAudience(p)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-all duration-150 ${
                    audience === p
                      ? "border-zinc-500 bg-zinc-800 text-zinc-200"
                      : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Proof story row */}
          <div className="p-6 space-y-3 border-b border-zinc-800">
            <div className="flex items-baseline justify-between">
              <label className="text-sm font-medium text-zinc-200">Client proof story</label>
              <span className="text-xs text-zinc-600">Optional</span>
            </div>
            <Textarea
              className="bg-zinc-950 border-zinc-700/80 text-zinc-100 text-sm placeholder:text-zinc-600 resize-none h-[88px] focus:ring-zinc-500 focus:border-zinc-500 rounded-lg"
              placeholder="e.g. Bora Ger scaled from $60K → $360K/year, calls 3 → 25/month..."
              value={clientStory}
              onChange={(e) => setClientStory(e.target.value)}
            />
            <p className="text-xs text-zinc-600">Leave blank to auto-pick the best matching case study from your brain.</p>
          </div>

          {/* Generate button row */}
          <div className="px-6 py-4 bg-zinc-900/80 flex items-center justify-between gap-4">
            <p className="text-xs text-zinc-600 hidden sm:block">Generates 3 variants: curiosity · outcome · mechanism</p>
            <button
              onClick={handleGenerate}
              disabled={loading || !audience.trim()}
              className="flex items-center gap-2 bg-zinc-100 hover:bg-white text-zinc-950 font-semibold text-sm px-6 py-2.5 rounded-lg transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed shrink-0 ml-auto"
            >
              {loading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-zinc-400 border-t-zinc-800 rounded-full animate-spin" />
                  Generating... {elapsed}s
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.93 2.93l1.41 1.41M9.66 9.66l1.41 1.41M2.93 11.07l1.41-1.41M9.66 4.34l1.41-1.41" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                  </svg>
                  Generate blockers
                </>
              )}
            </button>
          </div>

          {/* Progress bar — visible only while loading */}
          {loading && (
            <div className="px-6 pb-5 space-y-2">
              <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-zinc-400 rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${Math.min((elapsed / 30) * 100, 92)}%` }}
                />
              </div>
              <p className="text-xs text-zinc-500">
                {elapsed < 5
                  ? "Reading your brain context..."
                  : elapsed < 15
                  ? "Writing 3 variants..."
                  : elapsed < 25
                  ? "Almost there..."
                  : "Taking a little longer than usual..."}
              </p>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-500/8 px-4 py-3.5 text-sm text-red-400">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mt-0.5 shrink-0">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4"/>
              <path d="M8 5v3.5M8 11h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            {error}
          </div>
        )}

        {/* Output */}
        {variants.length > 0 && (
          <div className="space-y-5">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-medium text-zinc-400">3 variants for</h2>
              <span className="text-sm font-semibold text-zinc-200">{audience}</span>
            </div>

            <div className="space-y-4">
              {variants.map((v) => {
                const cfg = VARIANT_CONFIG[v.variant];
                return (
                  <div key={v.variant} className={`rounded-xl border ${cfg.border} ${cfg.bg} overflow-hidden`}>

                    {/* Card header */}
                    <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                        <span className={`text-xs font-semibold uppercase tracking-widest ${cfg.color}`}>
                          Variant {v.variant}
                        </span>
                        <span className="text-xs text-zinc-500">·</span>
                        <span className="text-xs text-zinc-400">{cfg.label}</span>
                        {v.style && (
                          <>
                            <span className="text-xs text-zinc-500">·</span>
                            <span className="text-xs text-zinc-500">{v.style}</span>
                          </>
                        )}
                      </div>
                      <CopyButton
                        onClick={() => copyFull(v)}
                        copied={copied === `${v.variant}-full`}
                      />
                    </div>

                    {/* Title */}
                    <div className="px-5 py-4 border-b border-white/5 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Title</span>
                        <div className="flex items-center gap-2.5">
                          <span className={`text-[11px] font-medium ${v.title.length > 60 ? "text-amber-400" : "text-zinc-600"}`}>
                            {v.title.length} chars {v.title.length > 60 ? "· may truncate" : ""}
                          </span>
                          <CopyButton
                            onClick={() => copy(`${v.variant}-title`, v.title)}
                            copied={copied === `${v.variant}-title`}
                          />
                        </div>
                      </div>
                      <p className="text-zinc-100 text-[15px] font-semibold leading-snug">{v.title}</p>
                    </div>

                    {/* Description */}
                    <div className="px-5 py-4 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Description</span>
                        <CopyButton
                          onClick={() => copy(`${v.variant}-description`, v.description)}
                          copied={copied === `${v.variant}-description`}
                        />
                      </div>
                      <pre className="text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap font-sans">{v.description}</pre>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && variants.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-16 space-y-3 text-center">
            <div className="w-10 h-10 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="2" y="3" width="14" height="12" rx="2" stroke="#52525b" strokeWidth="1.4"/>
                <path d="M6 3V1M12 3V1M2 7h14" stroke="#52525b" strokeWidth="1.4" strokeLinecap="round"/>
                <path d="M6 10.5h2M10 10.5h2M6 13h2" stroke="#52525b" strokeWidth="1.4" strokeLinecap="round"/>
              </svg>
            </div>
            <p className="text-sm text-zinc-500">Choose an audience above and hit generate.</p>
            <p className="text-xs text-zinc-600">Your brain will pick the best proof story and angle automatically.</p>
          </div>
        )}

      </div>
    </div>
  );
}
