"use client";

import { useState, useEffect, useRef } from "react";
import { Textarea } from "@/components/ui/textarea";
import { generateCalendarBlocker, CalendarVariant } from "@/lib/api";
import { addGeneration } from "@/lib/store";

const AUDIENCE_PRESETS = [
  "Fractional CFOs", "Fee-only RIAs", "B2B SaaS founders", "Agency owners",
  "Independent consultants", "Accounting firm owners", "Executive coaches", "Business exit advisors",
];

const VARIANT_CONFIG = {
  A: { label: "Curiosity", color: "text-violet-400", dot: "bg-violet-400", activeBg: "bg-violet-500/[0.06]" },
  B: { label: "Outcome",   color: "text-sky-400",    dot: "bg-sky-400",    activeBg: "bg-sky-500/[0.06]" },
  C: { label: "Mechanism", color: "text-emerald-400", dot: "bg-emerald-400", activeBg: "bg-emerald-500/[0.06]" },
} as const;

interface ResultGroup { audience: string; variants: CalendarVariant[]; }

function CopyBtn({ onClick, copied }: { onClick: () => void; copied: boolean }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1 text-[11px] font-medium px-2 py-[3px] rounded transition-all duration-100 ${
        copied ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-800 dark:text-zinc-300 hover:bg-zinc-200 dark:bg-zinc-700/40"
      }`}
    >
      {copied
        ? <><svg width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>Copied</>
        : <><svg width="10" height="10" viewBox="0 0 12 12" fill="none"><rect x="4" y="1" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M1 4.5V10a1 1 0 001 1h5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>Copy</>
      }
    </button>
  );
}

export function StudioPage() {
  const [audiences, setAudiences] = useState("");
  const [clientStory, setClientStory] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0, label: "" });
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ResultGroup[]>([]);
  const [copied, setCopied] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audienceList = audiences.split("\n").map((a) => a.trim()).filter(Boolean);

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } else { if (timerRef.current) clearInterval(timerRef.current); }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  async function handleGenerate() {
    if (!audienceList.length) return;
    setLoading(true); setError(null); setResults([]);
    const newResults: ResultGroup[] = [];
    try {
      for (let i = 0; i < audienceList.length; i++) {
        const aud = audienceList[i];
        setProgress({ current: i + 1, total: audienceList.length, label: aud });
        const result = await generateCalendarBlocker({ segment: aud, client_story: clientStory.trim() || undefined });
        const group = { audience: aud, variants: result.variants ?? [] };
        newResults.push(group); setResults([...newResults]);
        addGeneration({ format: "calendar-blocker", audience: aud, clientStory: clientStory.trim() || undefined, variants: result.variants ?? [] });
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong"); }
    finally { setLoading(false); }
  }

  function copy(key: string, text: string) {
    navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 2000);
  }
  function togglePreset(p: string) {
    const list = audiences.split("\n").map((a) => a.trim()).filter(Boolean);
    if (list.includes(p)) setAudiences(list.filter((a) => a !== p).join("\n"));
    else setAudiences(list.length > 0 ? audiences.trimEnd() + "\n" + p : p);
  }

  const statusLabel = progress.total > 1 ? `${progress.current} of ${progress.total} — ${progress.label}`
    : elapsed < 5 ? "Reading context..." : elapsed < 15 ? "Writing variants..." : elapsed < 25 ? "Almost there..." : "Just a moment...";

  return (
    <div className="min-h-[calc(100vh-48px)] bg-white dark:bg-zinc-950">
      <div className="max-w-3xl mx-auto px-6 py-12 space-y-8">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Content Studio</h1>
          <p className="text-sm text-zinc-500 mt-1.5">Generate high-converting copy for your next campaign.</p>
        </div>

        {/* Format picker */}
        <div className="space-y-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Format</p>
          <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
            <div className="flex items-center gap-2.5 px-4 py-2 rounded-md bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 shadow-sm">
              <span className="text-base leading-none select-none">📅</span>
              <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Calendar Blockers</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 rounded-md cursor-not-allowed opacity-30 select-none">
              <span className="text-base leading-none">📣</span>
              <span className="text-sm text-zinc-600 dark:text-zinc-400">Meta Ads</span>
              <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-500 ml-0.5">soon</span>
            </div>
          </div>
        </div>

        {/* Input card */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 overflow-hidden">
          <div className="p-6 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                {audienceList.length > 1 ? `Audiences · ${audienceList.length}` : "Audience"}
              </label>
              <span className="text-xs text-zinc-600">One per line for bulk</span>
            </div>
            <Textarea
              className="bg-white dark:bg-zinc-950 border-zinc-300 dark:border-zinc-700/60 text-zinc-900 dark:text-zinc-100 text-sm placeholder:text-zinc-700 resize-none h-[88px] focus-visible:ring-1 focus-visible:ring-zinc-500 focus-visible:border-zinc-500 rounded-lg"
              placeholder={"Fractional CFOs\nFee-only RIAs\nB2B SaaS founders"}
              value={audiences} onChange={(e) => setAudiences(e.target.value)} autoFocus
            />
            <div className="flex flex-wrap gap-1.5">
              {AUDIENCE_PRESETS.map((p) => (
                <button key={p} onClick={() => togglePreset(p)}
                  className={`text-xs px-3 py-1 rounded-full border transition-all duration-100 ${
                    audienceList.includes(p) ? "border-zinc-500 bg-zinc-200 dark:bg-zinc-700/50 text-zinc-800 dark:text-zinc-200" : "border-zinc-300 dark:border-zinc-700/60 text-zinc-500 hover:border-zinc-600 hover:text-zinc-800 dark:text-zinc-300"
                  }`}
                >{p}</button>
              ))}
            </div>
          </div>

          <div className="p-6 pt-0 space-y-3 border-t border-zinc-200 dark:border-zinc-800">
            <div className="flex items-center justify-between pt-5">
              <label className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Proof Story</label>
              <span className="text-xs text-zinc-600">Optional</span>
            </div>
            <Textarea
              className="bg-white dark:bg-zinc-950 border-zinc-300 dark:border-zinc-700/60 text-zinc-900 dark:text-zinc-100 text-sm placeholder:text-zinc-700 resize-none h-[80px] focus-visible:ring-1 focus-visible:ring-zinc-500 focus-visible:border-zinc-500 rounded-lg"
              placeholder="e.g. Bora Ger scaled from $60K → $360K/year, calls 3 → 25/month..."
              value={clientStory} onChange={(e) => setClientStory(e.target.value)}
            />
            <p className="text-xs text-zinc-600">Leave blank to auto-pick the best case study from your brain.</p>
          </div>

          <div className="px-6 py-4 bg-white dark:bg-zinc-950/50 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-4">
            <p className="text-xs text-zinc-600 hidden sm:block">
              {audienceList.length > 1 ? `${audienceList.length} × 3 = ${audienceList.length * 3} blockers` : "Generates curiosity · outcome · mechanism"}
            </p>
            <button onClick={handleGenerate} disabled={loading || !audienceList.length}
              className="flex items-center gap-2 bg-white hover:bg-zinc-100 text-zinc-900 font-semibold text-sm px-5 py-2.5 rounded-lg transition-colors duration-100 disabled:opacity-25 disabled:cursor-not-allowed ml-auto"
            >
              {loading
                ? <><span className="w-3.5 h-3.5 border-2 border-zinc-400 border-t-zinc-700 rounded-full animate-spin" />{progress.total > 1 ? `${progress.current}/${progress.total}` : `${elapsed}s`}</>
                : <><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.93 2.93l1.41 1.41M9.66 9.66l1.41 1.41M2.93 11.07l1.41-1.41M9.66 4.34l1.41-1.41" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>{audienceList.length > 1 ? `Generate × ${audienceList.length}` : "Generate"}</>
              }
            </button>
          </div>

          {loading && (
            <div className="px-6 pb-5 space-y-2 border-t border-zinc-200 dark:border-zinc-800/40">
              <div className="w-full h-[2px] bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden mt-4">
                {progress.total > 1
                  ? <div className="h-full bg-zinc-500 rounded-full transition-all duration-500" style={{ width: `${((progress.current - 1) / progress.total) * 100}%` }} />
                  : <div className="h-full bg-zinc-500 rounded-full transition-all duration-1000 ease-out" style={{ width: `${Math.min((elapsed / 30) * 100, 92)}%` }} />
                }
              </div>
              <p className="text-xs text-zinc-600">{statusLabel}</p>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-950/30 px-4 py-3 text-sm text-red-400">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="mt-0.5 shrink-0"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4"/><path d="M8 5v3.5M8 11h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
            {error}
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-600">
                {!loading && results.length === audienceList.length ? `${results.length} generated · saved` : `${results.length} / ${audienceList.length}`}
              </p>
              {!loading && <a href="/library" className="text-xs text-zinc-500 hover:text-zinc-800 dark:text-zinc-300 transition-colors">View in library →</a>}
            </div>
            {results.map((group, gi) => (
              <div key={gi} className="space-y-2">
                {results.length > 1 && <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400 px-1">{group.audience}</p>}
                <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 overflow-hidden">
                  {group.variants.map((v, vi) => {
                    const cfg = VARIANT_CONFIG[v.variant];
                    return (
                      <div key={v.variant} className={vi > 0 ? "border-t border-zinc-200 dark:border-zinc-800" : ""}>
                        <div className="flex items-center justify-between px-5 py-3 bg-white dark:bg-zinc-950/50">
                          <div className="flex items-center gap-2.5">
                            <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                            <span className={`text-[11px] font-semibold uppercase tracking-widest ${cfg.color}`}>{v.variant} · {cfg.label}</span>
                            {v.style && <span className="text-[11px] text-zinc-600">— {v.style}</span>}
                          </div>
                          <CopyBtn onClick={() => copy(`${gi}-${v.variant}-full`, `TITLE: ${v.title}\n\nDESCRIPTION:\n${v.description}`)} copied={copied === `${gi}-${v.variant}-full`} />
                        </div>
                        <div className={`px-5 py-4 border-t border-zinc-200 dark:border-zinc-800/40 ${cfg.activeBg}`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">Title</span>
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] ${v.title.length > 60 ? "text-amber-400/70" : "text-zinc-700"}`}>{v.title.length} chars{v.title.length > 60 ? " · may clip" : ""}</span>
                              <CopyBtn onClick={() => copy(`${gi}-${v.variant}-t`, v.title)} copied={copied === `${gi}-${v.variant}-t`} />
                            </div>
                          </div>
                          <p className="text-zinc-900 dark:text-zinc-100 text-[15px] font-semibold leading-snug">{v.title}</p>
                        </div>
                        <div className={`px-5 py-4 border-t border-zinc-200 dark:border-zinc-800/40 ${cfg.activeBg}`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">Description</span>
                            <CopyBtn onClick={() => copy(`${gi}-${v.variant}-d`, v.description)} copied={copied === `${gi}-${v.variant}-d`} />
                          </div>
                          <pre className="text-zinc-800 dark:text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap font-sans">{v.description}</pre>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !results.length && !error && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <div className="w-10 h-10 rounded-xl bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="2" y="3" width="14" height="12" rx="2" stroke="#52525b" strokeWidth="1.3"/>
                <path d="M6 3V1M12 3V1M2 7h14" stroke="#52525b" strokeWidth="1.3" strokeLinecap="round"/>
                <path d="M6 11h2M10 11h2M6 14h2" stroke="#52525b" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">Enter an audience above and generate.</p>
              <p className="text-xs text-zinc-600 mt-0.5">Output is auto-saved to your library.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
