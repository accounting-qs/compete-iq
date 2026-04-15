"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  fetchBuckets,
  generateCopies as apiGenerateCopies,
  createCopy as apiCreateCopy,
  updateCopy as apiUpdateCopy,
  regenerateCopy as apiRegenerateCopy,
  type ApiBucket,
  type ApiCopy,
} from "@/lib/api";
import { BrainPanel } from "./BrainPanel";

/* ─── Types ────────────────────────────────────────────────────────────── */

interface CopyVariant {
  id: string;
  text: string;
  isPrimary: boolean;
  isAssigned?: boolean;
}

interface GeneratedCopy {
  bucketId: string;
  type: "title" | "description";
  variants: CopyVariant[];
  generatedAt: string;
}

type GenerationStatus = "idle" | "generating" | "done";

/* ─── Helpers: Convert API types to local types ────────────────────────── */

function apiCopyToVariant(c: ApiCopy): CopyVariant {
  return { id: c.id, text: c.text, isPrimary: c.is_primary, isAssigned: c.is_assigned };
}

/* ─── Country Badge ────────────────────────────────────────────────────── */

function CountryBadge({ code }: { code: string }) {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-100 dark:bg-zinc-800/60 text-zinc-500 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700/40">
      {code}
    </span>
  );
}

/* ─── Variations Modal ─────────────────────────────────────────────────── */

function VariationsModal({
  bucket,
  initialTab,
  titles,
  descriptions,
  onClose,
  onUpdateVariant,
  onSetPrimary,
  onRegenerate,
  onAddVariant,
}: {
  bucket: ApiBucket;
  initialTab: "title" | "description";
  titles: CopyVariant[];
  descriptions: CopyVariant[];
  onClose: () => void;
  onUpdateVariant: (bucketId: string, type: "title" | "description", variantId: string, newText: string) => void;
  onSetPrimary: (bucketId: string, type: "title" | "description", variantId: string) => void;
  onRegenerate: (bucketId: string, type: "title" | "description", copyId: string, feedback: string) => Promise<void>;
  onAddVariant: (bucketId: string, type: "title" | "description", text: string) => Promise<void>;
}) {
  const [activeTab, setActiveTab] = useState<"title" | "description">(initialTab);
  const [feedback, setFeedback] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  const [regeneratingIds, setRegeneratingIds] = useState<Set<string>>(new Set());
  const [selectedForRegen, setSelectedForRegen] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [addingManual, setAddingManual] = useState(false);
  const [manualText, setManualText] = useState("");
  const [generatingNew, setGeneratingNew] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const manualTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textareas to match content height
  useEffect(() => {
    const ta = editTextareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${ta.scrollHeight}px`;
    }
  }, [editText, editingId]);

  useEffect(() => {
    const ta = manualTextareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${ta.scrollHeight}px`;
      ta.focus();
    }
  }, [addingManual, manualText]);

  const variants = activeTab === "title" ? titles : descriptions;

  // Clear selection when switching tabs
  const switchTab = useCallback((tab: "title" | "description") => {
    setActiveTab(tab);
    setSelectedForRegen(new Set());
  }, []);

  const toggleRegenSelect = useCallback((id: string) => {
    setSelectedForRegen(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const handleCopy = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  const handleStartEdit = useCallback((id: string, text: string) => {
    setEditingId(id);
    setEditText(text);
  }, []);

  const handleSaveEdit = useCallback((variantId: string) => {
    onUpdateVariant(bucket.id, activeTab, variantId, editText);
    setEditingId(null);
    setEditText("");
  }, [bucket.id, activeTab, editText, onUpdateVariant]);

  const handleRegenerate = useCallback(async () => {
    if (!feedback.trim()) return;
    const targetIds = selectedForRegen.size > 0
      ? Array.from(selectedForRegen)
      : [];
    if (targetIds.length === 0) return;

    setRegenerating(true);
    setRegeneratingIds(new Set(targetIds));

    for (const copyId of targetIds) {
      await onRegenerate(bucket.id, activeTab, copyId, feedback);
      setRegeneratingIds(prev => {
        const next = new Set(prev);
        next.delete(copyId);
        return next;
      });
    }

    setFeedback("");
    setSelectedForRegen(new Set());
    setRegenerating(false);
    setRegeneratingIds(new Set());
  }, [feedback, activeTab, bucket, selectedForRegen, onRegenerate]);

  const handleGenerateNew = useCallback(async () => {
    if (!feedback.trim() || variants.length === 0) return;
    setGeneratingNew(true);
    // Use the primary (or first) variant as a base for the AI to riff on with the user's direction
    const base = variants.find(v => v.isPrimary) || variants[0];
    await onRegenerate(bucket.id, activeTab, base.id, feedback);
    setFeedback("");
    setGeneratingNew(false);
  }, [feedback, activeTab, bucket, variants, onRegenerate]);

  const handleAddManual = useCallback(async () => {
    if (!manualText.trim()) return;
    await onAddVariant(bucket.id, activeTab, manualText.trim());
    setManualText("");
    setAddingManual(false);
  }, [manualText, activeTab, bucket, onAddVariant]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800/60 shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">

        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-zinc-200 dark:border-zinc-800/40 shrink-0">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100 truncate">{bucket.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-zinc-500">{bucket.industry}</span>
              <span className="text-zinc-300 dark:text-zinc-600">·</span>
              <span className="text-xs text-zinc-500">{bucket.remaining_contacts.toLocaleString()} remaining</span>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* ── Tab Bar ─────────────────────────────────────────────── */}
        <div className="flex items-center gap-1 px-6 py-2.5 border-b border-zinc-200 dark:border-zinc-800/40 shrink-0">
          <button
            onClick={() => switchTab("title")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "title"
                ? "bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 border border-violet-200 dark:border-violet-500/25"
                : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
            }`}
          >
            Titles ({titles.length})
          </button>
          <button
            onClick={() => switchTab("description")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "description"
                ? "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/25"
                : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
            }`}
          >
            Descriptions ({descriptions.length})
          </button>
        </div>

        {/* ── Variants List ───────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {variants.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-zinc-400 text-sm">
              No {activeTab === "title" ? "titles" : "descriptions"} generated yet
            </div>
          ) : (
            variants.map((v, i) => {
              const isEditing = editingId === v.id;
              const isSelectedForRegen = selectedForRegen.has(v.id);
              const isRegenerating = regeneratingIds.has(v.id);
              return (
                <div
                  key={v.id}
                  className={`rounded-xl border transition-all ${
                    isSelectedForRegen
                      ? "border-amber-300 dark:border-amber-500/40 bg-amber-50/50 dark:bg-amber-500/5 ring-1 ring-amber-300/50 dark:ring-amber-500/20"
                      : v.isPrimary
                        ? activeTab === "title"
                          ? "border-violet-300 dark:border-violet-500/30 bg-violet-50/50 dark:bg-violet-500/5"
                          : "border-blue-300 dark:border-blue-500/30 bg-blue-50/50 dark:bg-blue-500/5"
                        : "border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900/60"
                  } ${isRegenerating ? "opacity-60" : ""}`}
                >
                  <div className="px-4 py-3">
                    {/* Top row: number + actions */}
                    <div className="flex items-center gap-2 mb-2">
                      <button
                        onClick={() => toggleRegenSelect(v.id)}
                        className={`shrink-0 w-5 h-5 flex items-center justify-center rounded text-[10px] font-bold transition-all ${
                          isSelectedForRegen
                            ? "bg-amber-400 dark:bg-amber-500 text-white ring-1 ring-amber-500/50"
                            : activeTab === "title"
                              ? "bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 hover:bg-violet-200 dark:hover:bg-violet-500/25"
                              : "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/25"
                        }`}
                        title={isSelectedForRegen ? "Deselect for regeneration" : "Select for regeneration"}
                      >
                        {isSelectedForRegen ? "✓" : i + 1}
                      </button>
                      {v.isPrimary && (
                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                          activeTab === "title"
                            ? "bg-violet-200/60 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400"
                            : "bg-blue-200/60 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400"
                        }`}>
                          Primary
                        </span>
                      )}
                      {v.isAssigned && (
                        <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-200/60 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                          Picked
                        </span>
                      )}
                      <span className="text-[10px] text-zinc-400 font-mono">{v.text.length} chars{activeTab === "description" ? ` · ${v.text.trim().split(/\s+/).length} words` : ""}</span>
                      <div className="flex-1" />

                      {/* Actions */}
                      <div className="flex items-center gap-1">
                        {!v.isPrimary && (
                          <button
                            onClick={() => onSetPrimary(bucket.id, activeTab, v.id)}
                            className="text-[10px] font-medium px-2 py-1 rounded-md text-zinc-500 hover:text-violet-500 hover:bg-violet-50 dark:hover:bg-violet-500/10 transition-colors"
                          >
                            Set Primary
                          </button>
                        )}
                        {!isEditing ? (
                          <button
                            onClick={() => handleStartEdit(v.id, v.text)}
                            className="text-[10px] font-medium px-2 py-1 rounded-md text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 transition-colors"
                          >
                            Edit
                          </button>
                        ) : (
                          <button
                            onClick={() => handleSaveEdit(v.id)}
                            className="text-[10px] font-medium px-2 py-1 rounded-md text-emerald-500 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
                          >
                            Save
                          </button>
                        )}
                        <button
                          onClick={() => handleCopy(v.id, v.text)}
                          className={`text-[10px] font-medium px-2 py-1 rounded-md transition-colors ${
                            copiedId === v.id
                              ? "text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10"
                              : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/50"
                          }`}
                        >
                          {copiedId === v.id ? "Copied!" : "Copy"}
                        </button>
                      </div>
                    </div>

                    {/* Text content */}
                    {isRegenerating ? (
                      <div className="flex items-center gap-2 py-2 text-amber-500 text-xs font-medium">
                        <LoadingSpinner /> Regenerating this variant…
                      </div>
                    ) : isEditing ? (
                      <textarea
                        ref={editTextareaRef}
                        value={editText}
                        onChange={(e) => {
                          setEditText(e.target.value);
                          // Live auto-resize
                          const ta = e.target;
                          ta.style.height = "auto";
                          ta.style.height = `${ta.scrollHeight}px`;
                        }}
                        className="w-full bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed focus:outline-none focus:ring-2 focus:ring-violet-500/50 resize-vertical min-h-[60px] font-sans whitespace-pre-wrap"
                        autoFocus
                        onKeyDown={(e) => { if (e.key === "Escape") { setEditingId(null); } }}
                      />
                    ) : (
                      <pre
                        className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed cursor-text whitespace-pre-wrap font-sans"
                        onClick={() => handleStartEdit(v.id, v.text)}
                      >
                        {v.text}
                      </pre>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* ── Add Manual Variant ─────────────────────────────────── */}
          {addingManual ? (
            <div className="rounded-xl border border-dashed border-emerald-300 dark:border-emerald-500/30 bg-emerald-50/30 dark:bg-emerald-500/5 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  New manual variant
                </span>
              </div>
              <textarea
                ref={manualTextareaRef}
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder={`Type your ${activeTab} text here…`}
                className="w-full bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-vertical min-h-[60px] font-sans whitespace-pre-wrap"
                onKeyDown={(e) => {
                  if (e.key === "Escape") { setAddingManual(false); setManualText(""); }
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleAddManual(); }
                }}
              />
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={handleAddManual}
                  disabled={!manualText.trim()}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  Add variant
                </button>
                <button
                  onClick={() => { setAddingManual(false); setManualText(""); }}
                  className="px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 transition-colors"
                >
                  Cancel
                </button>
                <span className="text-[10px] text-zinc-400 ml-auto">Cmd+Enter to save</span>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAddingManual(true)}
              className="w-full rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700/40 hover:border-zinc-400 dark:hover:border-zinc-600 py-3 text-xs font-medium text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors flex items-center justify-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              Add variant manually
            </button>
          )}
        </div>

        {/* ── AI Generator ─────────────────────────────────────────── */}
        <div className="shrink-0 border-t border-zinc-200 dark:border-zinc-800/40 px-6 py-4 bg-zinc-50/50 dark:bg-zinc-800/20">
          <div className="flex items-center gap-2 mb-2">
            <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
              AI Copy Generator
            </label>
            {selectedForRegen.size > 0 ? (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-500/25">
                {selectedForRegen.size} variant{selectedForRegen.size !== 1 ? "s" : ""} selected — will regenerate
              </span>
            ) : (
              <span className="text-[10px] text-zinc-400">
                describe what you want — generates a new variant, or select variants to regenerate them
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (selectedForRegen.size > 0) handleRegenerate();
                  else handleGenerateNew();
                }
              }}
              placeholder={selectedForRegen.size > 0
                ? `Describe how to improve the ${selectedForRegen.size} selected variant${selectedForRegen.size !== 1 ? "s" : ""}…`
                : `e.g. "Make it about ROI", "Shorter and punchier", "Focus on AI angle"…`
              }
              className="flex-1 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700/60 rounded-lg px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-colors"
              disabled={regenerating || generatingNew}
            />
            {selectedForRegen.size > 0 ? (
              <button
                onClick={handleRegenerate}
                disabled={!feedback.trim() || regenerating}
                className="px-4 py-2 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 shrink-0"
              >
                {regenerating && <LoadingSpinner />}
                {regenerating
                  ? `Regenerating${regeneratingIds.size > 0 ? ` (${regeneratingIds.size} left)` : ""}…`
                  : `Regenerate ${selectedForRegen.size} variant${selectedForRegen.size !== 1 ? "s" : ""}`
                }
              </button>
            ) : (
              <button
                onClick={handleGenerateNew}
                disabled={!feedback.trim() || generatingNew || variants.length === 0}
                className="px-4 py-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 shrink-0"
              >
                {generatingNew && <LoadingSpinner />}
                {generatingNew ? "Generating…" : "Generate new variant"}
              </button>
            )}
          </div>
        </div>

        {/* ── Footer ──────────────────────────────────────────────── */}
        <div className="shrink-0 flex items-center justify-end px-6 py-3 border-t border-zinc-200 dark:border-zinc-800/40">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-zinc-900 dark:bg-zinc-100 hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-semibold rounded-lg transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────────────────── */

export function CopyGeneratorPage() {
  const [buckets, setBuckets] = useState<ApiBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [variantCount, setVariantCount] = useState(3);
  const [generatedCopies, setGeneratedCopies] = useState<Map<string, GeneratedCopy[]>>(new Map());
  const [statusMap, setStatusMap] = useState<Map<string, GenerationStatus>>(new Map());
  const [activeAction, setActiveAction] = useState<"title" | "description" | "both" | null>(null);
  const [modalState, setModalState] = useState<{ bucketId: string; tab: "title" | "description" } | null>(null);
  const [editingCell, setEditingCell] = useState<{ bucketId: string; type: "title" | "description" } | null>(null);
  const [editCellText, setEditCellText] = useState("");
  const editRef = useRef<HTMLTextAreaElement>(null);

  /* ── Load buckets with copies from API on mount ─────────────────────── */
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { buckets: apiBuckets } = await fetchBuckets(true);
        if (cancelled) return;
        setBuckets(apiBuckets);

        // Restore generated copies from API data
        const restored = new Map<string, GeneratedCopy[]>();
        const restoredStatus = new Map<string, GenerationStatus>();
        for (const b of apiBuckets) {
          const copies: GeneratedCopy[] = [];
          if (b.titles && b.titles.length > 0) {
            copies.push({
              bucketId: b.id, type: "title",
              variants: b.titles.map(apiCopyToVariant),
              generatedAt: b.titles[0]?.created_at || "",
            });
            restoredStatus.set(`${b.id}-title`, "done");
          }
          if (b.descriptions && b.descriptions.length > 0) {
            copies.push({
              bucketId: b.id, type: "description",
              variants: b.descriptions.map(apiCopyToVariant),
              generatedAt: b.descriptions[0]?.created_at || "",
            });
            restoredStatus.set(`${b.id}-description`, "done");
          }
          if (copies.length > 0) restored.set(b.id, copies);
        }
        setGeneratedCopies(restored);
        setStatusMap(restoredStatus);
      } catch (err) {
        console.error("Failed to load buckets:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  /* ── Selection ───────────────────────────────────────────────────────── */

  const allSelected = buckets.length > 0 && selectedIds.size === buckets.length;
  const someSelected = selectedIds.size > 0;

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(buckets.map(b => b.id)));
  };

  /* ── Generation (calls API) ─────────────────────────────────────────── */

  const doGenerateCopies = async (type: "title" | "description" | "both") => {
    if (selectedIds.size === 0) return;
    setActiveAction(type);

    const newStatusMap = new Map(statusMap);
    selectedIds.forEach(id => {
      if (type === "title" || type === "both") newStatusMap.set(`${id}-title`, "generating");
      if (type === "description" || type === "both") newStatusMap.set(`${id}-description`, "generating");
    });
    setStatusMap(newStatusMap);

    const selectedBuckets = buckets.filter(b => selectedIds.has(b.id));
    for (const bucket of selectedBuckets) {
      try {
        const result = await apiGenerateCopies(bucket.id, {
          copy_type: type,
          variant_count: variantCount,
        });

        setGeneratedCopies(prev => {
          const next = new Map(prev);
          const existing = next.get(bucket.id) || [];

          if ((type === "title" || type === "both") && result.titles.length > 0) {
            const titleCopy: GeneratedCopy = {
              bucketId: bucket.id, type: "title",
              variants: result.titles.map(apiCopyToVariant),
              generatedAt: new Date().toLocaleTimeString(),
            };
            const filtered = existing.filter(c => c.type !== "title");
            filtered.push(titleCopy);
            next.set(bucket.id, filtered);
          }

          if ((type === "description" || type === "both") && result.descriptions.length > 0) {
            const current = next.get(bucket.id) || [];
            const descCopy: GeneratedCopy = {
              bucketId: bucket.id, type: "description",
              variants: result.descriptions.map(apiCopyToVariant),
              generatedAt: new Date().toLocaleTimeString(),
            };
            const filtered = current.filter(c => c.type !== "description");
            filtered.push(descCopy);
            next.set(bucket.id, filtered);
          }

          return next;
        });

        setStatusMap(prev => {
          const next = new Map(prev);
          if (type === "title" || type === "both") next.set(`${bucket.id}-title`, "done");
          if (type === "description" || type === "both") next.set(`${bucket.id}-description`, "done");
          return next;
        });
      } catch (err) {
        console.error(`Failed to generate copies for ${bucket.name}:`, err);
        setStatusMap(prev => {
          const next = new Map(prev);
          if (type === "title" || type === "both") next.set(`${bucket.id}-title`, "idle");
          if (type === "description" || type === "both") next.set(`${bucket.id}-description`, "idle");
          return next;
        });
      }
    }

    setActiveAction(null);
  };

  /* ── Helpers ─────────────────────────────────────────────────────────── */

  const getStatus = (bucketId: string, type: string): GenerationStatus =>
    statusMap.get(`${bucketId}-${type}`) || "idle";

  const getCopies = (bucketId: string, type: "title" | "description"): CopyVariant[] => {
    const copies = generatedCopies.get(bucketId);
    if (!copies) return [];
    const found = copies.find(c => c.type === type);
    return found ? found.variants : [];
  };

  const getPrimary = (bucketId: string, type: "title" | "description"): CopyVariant | null => {
    const variants = getCopies(bucketId, type);
    return variants.find(v => v.isPrimary) || variants[0] || null;
  };

  const hasCopies = (bucketId: string): boolean => {
    const copies = generatedCopies.get(bucketId);
    return !!copies && copies.length > 0;
  };

  /* ── Mutation helpers (API-backed) ──────────────────────────────────── */

  const updateVariantText = useCallback(async (bucketId: string, type: "title" | "description", variantId: string, newText: string) => {
    // Optimistic update
    setGeneratedCopies(prev => {
      const next = new Map(prev);
      const copies = (next.get(bucketId) || []).map(c => {
        if (c.type !== type) return c;
        return { ...c, variants: c.variants.map(v => v.id === variantId ? { ...v, text: newText } : v) };
      });
      next.set(bucketId, copies);
      return next;
    });
    // Fire API call
    try {
      await apiUpdateCopy(variantId, { text: newText });
    } catch (err) {
      console.error("Failed to update copy:", err);
    }
  }, []);

  const setPrimaryVariant = useCallback(async (bucketId: string, type: "title" | "description", variantId: string) => {
    // Optimistic update — variants
    setGeneratedCopies(prev => {
      const next = new Map(prev);
      const copies = (next.get(bucketId) || []).map(c => {
        if (c.type !== type) return c;
        return { ...c, variants: c.variants.map(v => ({ ...v, isPrimary: v.id === variantId })) };
      });
      next.set(bucketId, copies);
      return next;
    });
    // Optimistic update — bucket-level picked flag
    setBuckets(prev => prev.map(b => {
      if (b.id !== bucketId) return b;
      return type === "title"
        ? { ...b, title_primary_picked: true }
        : { ...b, desc_primary_picked: true };
    }));
    // Fire API call
    try {
      await apiUpdateCopy(variantId, { is_primary: true });
    } catch (err) {
      console.error("Failed to set primary:", err);
    }
  }, []);

  const handleRegenerate = useCallback(async (bucketId: string, type: "title" | "description", copyId: string, feedback: string) => {
    try {
      const newCopy = await apiRegenerateCopy(copyId, feedback);
      // Add the new variant to local state
      setGeneratedCopies(prev => {
        const next = new Map(prev);
        const copies = (next.get(bucketId) || []).map(c => {
          if (c.type !== type) return c;
          return { ...c, variants: [...c.variants, apiCopyToVariant(newCopy)] };
        });
        next.set(bucketId, copies);
        return next;
      });
    } catch (err) {
      console.error("Failed to regenerate copy:", err);
    }
  }, []);

  const handleAddVariant = useCallback(async (bucketId: string, type: "title" | "description", text: string) => {
    try {
      const newCopy = await apiCreateCopy(bucketId, { copy_type: type, text });
      setGeneratedCopies(prev => {
        const next = new Map(prev);
        const existing = next.get(bucketId) || [];
        const found = existing.find(c => c.type === type);
        if (found) {
          const copies = existing.map(c => {
            if (c.type !== type) return c;
            return { ...c, variants: [...c.variants, apiCopyToVariant(newCopy)] };
          });
          next.set(bucketId, copies);
        } else {
          existing.push({
            bucketId, type,
            variants: [apiCopyToVariant(newCopy)],
            generatedAt: new Date().toLocaleTimeString(),
          });
          next.set(bucketId, existing);
        }
        return next;
      });
    } catch (err) {
      console.error("Failed to add variant:", err);
    }
  }, []);

  /* ── Inline edit handlers ────────────────────────────────────────────── */

  const startInlineEdit = (bucketId: string, type: "title" | "description", text: string) => {
    setEditingCell({ bucketId, type });
    setEditCellText(text);
  };

  const saveInlineEdit = () => {
    if (!editingCell) return;
    const primary = getPrimary(editingCell.bucketId, editingCell.type);
    if (primary) {
      updateVariantText(editingCell.bucketId, editingCell.type, primary.id, editCellText);
    }
    setEditingCell(null);
    setEditCellText("");
  };

  useEffect(() => {
    if (editingCell && editRef.current) editRef.current.focus();
  }, [editingCell]);

  const totalGenerated = Array.from(generatedCopies.values()).reduce((sum, copies) => sum + copies.length, 0);

  // Get modal bucket data
  const modalBucket = modalState ? buckets.find(b => b.id === modalState.bucketId) : null;

  /* ── Render ──────────────────────────────────────────────────────────── */

  if (loading) {
    return (
      <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0 flex items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-400">
          <LoadingSpinner /> Loading buckets…
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 bg-zinc-50 dark:bg-zinc-950 min-h-0">
      <div className="px-6 py-5 max-w-[1600px] mx-auto">

        {/* ── Page Header ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Calendar Invite Copy Generator</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">Generate calendar invite titles and descriptions for your outreach buckets.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-lg px-3 py-1.5">
              <span className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Buckets</span>
              <span className="text-sm font-bold text-zinc-800 dark:text-zinc-200 font-mono">{buckets.length}</span>
            </div>
            {totalGenerated > 0 && (
              <div className="flex items-center gap-2 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 rounded-lg px-3 py-1.5">
                <span className="text-[11px] text-violet-600 dark:text-violet-400 uppercase tracking-wider font-medium">Generated</span>
                <span className="text-sm font-bold text-violet-600 dark:text-violet-400 font-mono">{totalGenerated}</span>
              </div>
            )}
          </div>
        </div>

        {/* ── Brain Panel ──────────────────────────────────────────────── */}
        <div className="mb-4">
          <BrainPanel />
        </div>

        {/* ── Floating Action Bar ──────────────────────────────────────── */}
        {someSelected && (
          <div className="mb-4 flex items-center gap-3 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-xl px-4 py-3 shadow-sm">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
              {selectedIds.size} bucket{selectedIds.size !== 1 ? "s" : ""} selected
            </span>
            <div className="w-px h-5 bg-zinc-200 dark:bg-zinc-700" />
            <div className="flex items-center gap-2">
              <label className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">Variations</label>
              <input
                type="number" min={1} max={10} value={variantCount}
                onChange={(e) => setVariantCount(Math.max(1, Math.min(10, parseInt(e.target.value) || 3)))}
                className="w-14 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700/60 rounded-md px-2 py-1 text-sm text-zinc-800 dark:text-zinc-200 font-mono text-center focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
            <div className="w-px h-5 bg-zinc-200 dark:bg-zinc-700" />
            <button onClick={() => doGenerateCopies("title")} disabled={activeAction !== null}
              className="px-4 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-wait text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
              {activeAction === "title" && <LoadingSpinner />} Generate Titles
            </button>
            <button onClick={() => doGenerateCopies("description")} disabled={activeAction !== null}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-wait text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
              {activeAction === "description" && <LoadingSpinner />} Generate Descriptions
            </button>
            <button onClick={() => doGenerateCopies("both")} disabled={activeAction !== null}
              className="px-4 py-1.5 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-wait text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5">
              {activeAction === "both" && <LoadingSpinner />} Generate Both
            </button>
          </div>
        )}

        {/* ── Buckets Table ────────────────────────────────────────────── */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800/40 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-zinc-50 dark:bg-zinc-800/30 border-b border-zinc-200 dark:border-zinc-800/40">
                <th className="w-10 px-3 py-2.5">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll}
                    className="w-3.5 h-3.5 rounded border-zinc-300 dark:border-zinc-600 text-violet-600 focus:ring-violet-500 cursor-pointer accent-violet-600" />
                </th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[180px]">Bucket</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[90px]">Industry</th>
                <th className="text-right px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[70px]">Total</th>
                <th className="text-right px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[80px]">Remaining</th>
                <th className="text-center px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[100px]">Countries</th>
                <th className="text-center px-3 py-2.5 text-[11px] text-zinc-500 uppercase tracking-wider font-medium w-[60px]">Emp</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-violet-500 dark:text-violet-400 uppercase tracking-wider font-medium">Title</th>
                <th className="text-left px-3 py-2.5 text-[11px] text-blue-500 dark:text-blue-400 uppercase tracking-wider font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((bucket) => {
                const isSelected = selectedIds.has(bucket.id);
                const titleStatus = getStatus(bucket.id, "title");
                const descStatus = getStatus(bucket.id, "description");
                const primaryTitle = getPrimary(bucket.id, "title");
                const primaryDesc = getPrimary(bucket.id, "description");
                const titleVariants = getCopies(bucket.id, "title");
                const descVariants = getCopies(bucket.id, "description");
                const primaryTitleIdx = titleVariants.findIndex(v => v.isPrimary);
                const primaryDescIdx = descVariants.findIndex(v => v.isPrimary);
                const isTitleEditing = editingCell?.bucketId === bucket.id && editingCell?.type === "title";
                const isDescEditing = editingCell?.bucketId === bucket.id && editingCell?.type === "description";

                return (
                  <tr
                    key={bucket.id}
                    className={`border-b border-zinc-100 dark:border-zinc-800/30 transition-colors ${
                      isSelected ? "bg-violet-50/50 dark:bg-violet-500/5" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/20"
                    }`}
                  >
                    <td className="px-3 py-3">
                      <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(bucket.id)}
                        className="w-3.5 h-3.5 rounded border-zinc-300 dark:border-zinc-600 text-violet-600 focus:ring-violet-500 cursor-pointer accent-violet-600" />
                    </td>
                    <td className="px-3 py-3 font-medium text-zinc-800 dark:text-zinc-200 text-[13px]">{bucket.name}</td>
                    <td className="px-3 py-3 text-zinc-500 dark:text-zinc-400 text-xs">{bucket.industry}</td>
                    <td className="px-3 py-3 text-right font-mono text-zinc-700 dark:text-zinc-300 text-xs">{bucket.total_contacts.toLocaleString()}</td>
                    <td className="px-3 py-3 text-right font-mono text-violet-600 dark:text-violet-400 text-xs">{bucket.remaining_contacts.toLocaleString()}</td>
                    <td className="px-3 py-3 text-center">
                      <div className="flex gap-1 justify-center">{(bucket.countries || []).map(c => <CountryBadge key={c} code={c} />)}</div>
                    </td>
                    <td className="px-3 py-3 text-center text-xs text-zinc-500 font-mono">{bucket.emp_range}</td>

                    {/* ── Title Cell ───────────────────────────────── */}
                    <td className="px-3 py-2">
                      {titleStatus === "generating" ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-amber-500 font-medium">
                          <LoadingSpinner /> Generating…
                        </span>
                      ) : primaryTitle ? (
                        <div className="max-w-[280px]">
                          {isTitleEditing ? (
                            <textarea
                              ref={editRef}
                              value={editCellText}
                              onChange={(e) => setEditCellText(e.target.value)}
                              onBlur={saveInlineEdit}
                              onKeyDown={(e) => { if (e.key === "Escape") setEditingCell(null); if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveInlineEdit(); } }}
                              className="w-full bg-white dark:bg-zinc-800 border border-violet-400 dark:border-violet-500/50 rounded px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 leading-relaxed focus:outline-none focus:ring-1 focus:ring-violet-500 resize-none"
                              rows={2}
                            />
                          ) : (
                            <>
                              {(titleVariants.length > 1 || bucket.title_primary_picked) && (
                                <span className="inline-flex items-center gap-1 mb-1 flex-wrap">
                                  {titleVariants.length > 1 && primaryTitleIdx >= 0 && (
                                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400">
                                      Variant {primaryTitleIdx + 1}
                                    </span>
                                  )}
                                  {bucket.title_primary_picked && (
                                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                                      Primary picked
                                    </span>
                                  )}
                                </span>
                              )}
                              <p
                                className="text-xs text-zinc-700 dark:text-zinc-300 leading-snug line-clamp-2 cursor-text hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                                onClick={() => startInlineEdit(bucket.id, "title", primaryTitle.text)}
                                title={primaryTitle.text}
                              >
                                {primaryTitle.text}
                              </p>
                            </>
                          )}
                          {titleVariants.length > 1 && (
                            <button
                              onClick={() => setModalState({ bucketId: bucket.id, tab: "title" })}
                              className="text-[10px] text-violet-500 hover:text-violet-400 font-medium mt-1 transition-colors"
                            >
                              {titleVariants.length} variations →
                            </button>
                          )}
                          {titleVariants.length === 1 && (
                            <button
                              onClick={() => setModalState({ bucketId: bucket.id, tab: "title" })}
                              className="text-[10px] text-zinc-400 hover:text-violet-400 font-medium mt-1 transition-colors"
                            >
                              View & edit →
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-zinc-300 dark:text-zinc-600">—</span>
                      )}
                    </td>

                    {/* ── Description Cell ─────────────────────────── */}
                    <td className="px-3 py-2">
                      {descStatus === "generating" ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-amber-500 font-medium">
                          <LoadingSpinner /> Generating…
                        </span>
                      ) : primaryDesc ? (
                        <div className="max-w-[320px]">
                          {isDescEditing ? (
                            <textarea
                              ref={editRef}
                              value={editCellText}
                              onChange={(e) => setEditCellText(e.target.value)}
                              onBlur={saveInlineEdit}
                              onKeyDown={(e) => { if (e.key === "Escape") setEditingCell(null); if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveInlineEdit(); } }}
                              className="w-full bg-white dark:bg-zinc-800 border border-blue-400 dark:border-blue-500/50 rounded px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 leading-relaxed focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                              rows={3}
                            />
                          ) : (
                            <>
                              {(descVariants.length > 1 || bucket.desc_primary_picked) && (
                                <span className="inline-flex items-center gap-1 mb-1 flex-wrap">
                                  {descVariants.length > 1 && primaryDescIdx >= 0 && (
                                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400">
                                      Variant {primaryDescIdx + 1}
                                    </span>
                                  )}
                                  {bucket.desc_primary_picked && (
                                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                                      Primary picked
                                    </span>
                                  )}
                                </span>
                              )}
                              <p
                                className="text-xs text-zinc-700 dark:text-zinc-300 leading-snug line-clamp-2 cursor-text hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                                onClick={() => startInlineEdit(bucket.id, "description", primaryDesc.text)}
                                title={primaryDesc.text}
                              >
                                {primaryDesc.text}
                              </p>
                            </>
                          )}
                          {descVariants.length > 1 && (
                            <button
                              onClick={() => setModalState({ bucketId: bucket.id, tab: "description" })}
                              className="text-[10px] text-blue-500 hover:text-blue-400 font-medium mt-1 transition-colors"
                            >
                              {descVariants.length} variations →
                            </button>
                          )}
                          {descVariants.length === 1 && (
                            <button
                              onClick={() => setModalState({ bucketId: bucket.id, tab: "description" })}
                              className="text-[10px] text-zinc-400 hover:text-blue-400 font-medium mt-1 transition-colors"
                            >
                              View & edit →
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-zinc-300 dark:text-zinc-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Modal ──────────────────────────────────────────────────────── */}
      {modalState && modalBucket && (
        <VariationsModal
          bucket={modalBucket}
          initialTab={modalState.tab}
          titles={getCopies(modalState.bucketId, "title")}
          descriptions={getCopies(modalState.bucketId, "description")}
          onClose={() => setModalState(null)}
          onUpdateVariant={updateVariantText}
          onSetPrimary={setPrimaryVariant}
          onRegenerate={handleRegenerate}
          onAddVariant={handleAddVariant}
        />
      )}
    </main>
  );
}

/* ─── Sub-components ───────────────────────────────────────────────────── */

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
