"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  releaseWebinarContacts,
  type ReleaseContactsResponse,
} from "@/lib/api";

type Step = "pick" | "map" | "submitting" | "done" | "error";

interface ParsedCsv {
  fileName: string;
  headers: string[];
  preview: string[][];
  rowCount: number;
  rows: string[][];
}

interface ReleaseProgress {
  processed: number;
  total: number;
  chunkIndex: number;
  chunkCount: number;
}

interface Props {
  webinarId: string;
  webinarNumber: number;
  onClose: () => void;
  /** Called after a successful release so the planning page can refetch
   * webinar lists / bucket counts to reflect the new totals. */
  onReleased: (result: ReleaseContactsResponse) => void;
}

// Send emails to the backend in 1k-row chunks. The server can handle larger
// payloads, but smaller chunks give a smoother progress bar (~30 ticks for a
// 30k-row CSV) and bound any individual request's blast radius.
const RELEASE_CHUNK_SIZE = 1000;

/** Minimal RFC4180-ish CSV parser. Handles quoted fields with embedded quotes
 * ("") and commas. The release CSV is expected to be small (an emails list)
 * so we parse the whole file in memory. */
function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const rows: string[][] = [];
  let cur: string[] = [];
  let field = "";
  let i = 0;
  let inQuotes = false;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i += 2; continue; }
      if (ch === '"') { inQuotes = false; i++; continue; }
      field += ch; i++; continue;
    }
    if (ch === '"') { inQuotes = true; i++; continue; }
    if (ch === ",") { cur.push(field); field = ""; i++; continue; }
    if (ch === "\r") { i++; continue; }
    if (ch === "\n") {
      cur.push(field); field = "";
      if (cur.some((c) => c.trim() !== "")) rows.push(cur);
      cur = []; i++; continue;
    }
    field += ch; i++;
  }
  // flush trailing field
  if (field.length > 0 || cur.length > 0) {
    cur.push(field);
    if (cur.some((c) => c.trim() !== "")) rows.push(cur);
  }
  if (rows.length === 0) return { headers: [], rows: [] };
  const [headers, ...body] = rows;
  return { headers: headers.map((h) => h.trim()), rows: body };
}

function detectEmailColumn(headers: string[]): string | null {
  const lower = headers.map((h) => h.toLowerCase());
  const exact = lower.findIndex((h) => h === "email" || h === "e-mail");
  if (exact >= 0) return headers[exact];
  const partial = lower.findIndex((h) => h.includes("email"));
  if (partial >= 0) return headers[partial];
  return null;
}

export function ReleaseContactsModal({ webinarId, webinarNumber, onClose, onReleased }: Props) {
  const [step, setStep] = useState<Step>("pick");
  const [parsed, setParsed] = useState<ParsedCsv | null>(null);
  const [emailColumn, setEmailColumn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReleaseContactsResponse | null>(null);
  const [progress, setProgress] = useState<ReleaseProgress | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Lock body scroll while open + close on Escape.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const emailIndex = useMemo(() => {
    if (!parsed || !emailColumn) return -1;
    return parsed.headers.indexOf(emailColumn);
  }, [parsed, emailColumn]);

  const extractedEmails = useMemo(() => {
    if (!parsed || emailIndex < 0) return [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const row of parsed.rows) {
      const raw = (row[emailIndex] ?? "").trim().toLowerCase();
      if (!raw) continue;
      if (seen.has(raw)) continue;
      seen.add(raw);
      out.push(raw);
    }
    return out;
  }, [parsed, emailIndex]);

  async function handleFile(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Please choose a .csv file.");
      return;
    }
    try {
      const text = await file.text();
      const { headers, rows } = parseCsv(text);
      if (headers.length === 0) {
        setError("CSV is empty.");
        return;
      }
      const detected = detectEmailColumn(headers);
      setParsed({
        fileName: file.name,
        headers,
        preview: rows.slice(0, 5),
        rowCount: rows.length,
        rows,
      });
      setEmailColumn(detected);
      setStep("map");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to read CSV.");
    }
  }

  async function handleSubmit() {
    if (extractedEmails.length === 0) {
      setError("No emails found in the selected column.");
      return;
    }
    setStep("submitting");
    setError(null);

    const chunks: string[][] = [];
    for (let i = 0; i < extractedEmails.length; i += RELEASE_CHUNK_SIZE) {
      chunks.push(extractedEmails.slice(i, i + RELEASE_CHUNK_SIZE));
    }

    setProgress({ processed: 0, total: extractedEmails.length, chunkIndex: 0, chunkCount: chunks.length });

    // Aggregate the per-chunk reports into a single response shape the UI
    // can render. We also reuse the batch_id from the first chunk so all
    // released contacts land in one audit-log batch.
    const aggregate: ReleaseContactsResponse = {
      release_batch_id: "",
      released: 0,
      not_found: [],
      already_available: [],
      by_status: { assigned: 0, used: 0 },
      bucket_updates: {},
    };

    try {
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const res = await releaseWebinarContacts(
          webinarId,
          chunk,
          aggregate.release_batch_id || undefined,
        );
        if (!aggregate.release_batch_id) aggregate.release_batch_id = res.release_batch_id;
        aggregate.released += res.released;
        aggregate.not_found.push(...res.not_found);
        aggregate.already_available.push(...res.already_available);
        aggregate.by_status.assigned += res.by_status.assigned;
        aggregate.by_status.used += res.by_status.used;
        // Last write wins — bucket_updates is the *current* available count
        // per bucket, so the latest chunk's value is the most accurate.
        Object.assign(aggregate.bucket_updates, res.bucket_updates);

        setProgress({
          processed: Math.min((i + 1) * RELEASE_CHUNK_SIZE, extractedEmails.length),
          total: extractedEmails.length,
          chunkIndex: i + 1,
          chunkCount: chunks.length,
        });
      }
      setResult(aggregate);
      setStep("done");
      onReleased(aggregate);
    } catch (e) {
      setError(
        e instanceof Error
          ? `${e.message} (released ${aggregate.released.toLocaleString()} contacts before the error — they're already saved)`
          : "Release failed.",
      );
      setStep("error");
      // Still notify the parent so the planning page reflects what *did* land.
      if (aggregate.released > 0) onReleased(aggregate);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Release unused contacts
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              Webinar {webinarNumber} — upload a CSV of emails you couldn't contact in time.
              Matching contacts are reverted to <span className="font-mono">available</span> in
              their original buckets so you can re-assign them. The planned send number is preserved.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            aria-label="Close"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {step === "pick" && (
            <div>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f) handleFile(f);
                }}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg p-10 text-center cursor-pointer hover:border-violet-500 hover:bg-violet-500/5 transition-colors"
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto text-zinc-400 mb-3">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  Drop a CSV here, or click to choose
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  Only the email column is used. Other fields are ignored.
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                  e.target.value = "";
                }}
              />
              {error && (
                <div className="mt-3 text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded p-2">
                  {error}
                </div>
              )}
            </div>
          )}

          {step === "map" && parsed && (
            <div>
              <div className="text-xs text-zinc-500 mb-3">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">{parsed.fileName}</span>
                {" — "}
                {parsed.rowCount.toLocaleString()} row{parsed.rowCount === 1 ? "" : "s"}.
                Pick the column that contains the emails to release.
              </div>

              <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-zinc-100 dark:bg-zinc-800/40">
                    <tr>
                      <th className="text-left px-3 py-2 font-semibold text-zinc-600 dark:text-zinc-400">CSV Column</th>
                      <th className="text-left px-3 py-2 font-semibold text-zinc-600 dark:text-zinc-400">Preview</th>
                      <th className="text-left px-3 py-2 font-semibold text-zinc-600 dark:text-zinc-400 w-32">Map To</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.headers.map((h, idx) => {
                      const isEmail = h === emailColumn;
                      return (
                        <tr
                          key={`${h}-${idx}`}
                          className={`border-t border-zinc-200 dark:border-zinc-800/40 ${isEmail ? "bg-violet-500/5" : ""}`}
                        >
                          <td className="px-3 py-2 font-medium text-zinc-800 dark:text-zinc-200">{h}</td>
                          <td className="px-3 py-2 text-zinc-500 truncate max-w-[200px]">
                            {parsed.preview[0]?.[idx] ?? "—"}
                          </td>
                          <td className="px-3 py-2">
                            <label className="inline-flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="radio"
                                name="email-col"
                                checked={isEmail}
                                onChange={() => setEmailColumn(h)}
                                className="accent-violet-500"
                              />
                              <span className={`text-xs ${isEmail ? "text-violet-500 font-semibold" : "text-zinc-500"}`}>
                                Email
                              </span>
                            </label>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {emailColumn && (
                <div className="mt-3 text-xs text-zinc-500">
                  Will release <span className="font-mono font-semibold text-zinc-700 dark:text-zinc-300">{extractedEmails.length.toLocaleString()}</span>
                  {" "}unique email{extractedEmails.length === 1 ? "" : "s"}
                  {extractedEmails.length !== parsed.rowCount && (
                    <> (<span className="font-mono">{(parsed.rowCount - extractedEmails.length).toLocaleString()}</span> blank/duplicate skipped)</>
                  )}
                  .
                </div>
              )}

              {error && (
                <div className="mt-3 text-sm text-red-500 bg-red-500/10 border border-red-500/30 rounded p-2">
                  {error}
                </div>
              )}
            </div>
          )}

          {step === "submitting" && progress && (
            <div className="py-10">
              <div className="text-center mb-4">
                <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  Releasing contacts…
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  Batch {progress.chunkIndex.toLocaleString()} of {progress.chunkCount.toLocaleString()}
                  {" — "}
                  {progress.processed.toLocaleString()} / {progress.total.toLocaleString()} emails
                </div>
              </div>
              <div className="h-2 w-full bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-500 transition-[width] duration-300 ease-out"
                  style={{
                    width: `${progress.total > 0 ? (progress.processed / progress.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="text-center mt-2 text-[11px] text-zinc-500 font-mono">
                {progress.total > 0
                  ? Math.round((progress.processed / progress.total) * 100)
                  : 0}
                %
              </div>
            </div>
          )}

          {step === "done" && result && (
            <div>
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded p-4 mb-4">
                <div className="text-sm font-semibold text-emerald-500 mb-1">
                  Released {result.released.toLocaleString()} contact{result.released === 1 ? "" : "s"}
                </div>
                <div className="text-xs text-zinc-600 dark:text-zinc-400">
                  {result.by_status.used.toLocaleString()} were marked sent · {result.by_status.assigned.toLocaleString()} were claimed but unsent.
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-zinc-100 dark:bg-zinc-800/40 rounded p-3">
                  <dt className="text-zinc-500 mb-0.5">Not found in this webinar</dt>
                  <dd className="text-base font-mono font-semibold text-zinc-800 dark:text-zinc-200">
                    {result.not_found.length.toLocaleString()}
                  </dd>
                </div>
                <div className="bg-zinc-100 dark:bg-zinc-800/40 rounded p-3">
                  <dt className="text-zinc-500 mb-0.5">Already available (skipped)</dt>
                  <dd className="text-base font-mono font-semibold text-zinc-800 dark:text-zinc-200">
                    {result.already_available.length.toLocaleString()}
                  </dd>
                </div>
              </dl>

              {result.not_found.length > 0 && (
                <details className="mt-3 text-xs">
                  <summary className="cursor-pointer text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
                    Show {result.not_found.length.toLocaleString()} not-found email{result.not_found.length === 1 ? "" : "s"}
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-y-auto bg-zinc-100 dark:bg-zinc-800/60 p-2 rounded text-zinc-600 dark:text-zinc-400 text-[11px] font-mono whitespace-pre-wrap break-all">
                    {result.not_found.slice(0, 200).join("\n")}
                    {result.not_found.length > 200 && `\n…and ${result.not_found.length - 200} more`}
                  </pre>
                </details>
              )}

              {Object.keys(result.bucket_updates).length > 0 && (
                <div className="mt-3 text-xs text-zinc-500">
                  {Object.keys(result.bucket_updates).length} bucket{Object.keys(result.bucket_updates).length === 1 ? "" : "s"} refreshed with the restored available counts.
                </div>
              )}
            </div>
          )}

          {step === "error" && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-4 text-sm text-red-500">
              {error ?? "Unknown error."}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2">
          {step === "map" && (
            <>
              <button
                onClick={() => { setParsed(null); setEmailColumn(null); setStep("pick"); }}
                className="px-3 py-1.5 text-xs font-semibold rounded border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Back
              </button>
              <button
                disabled={!emailColumn || extractedEmails.length === 0}
                onClick={handleSubmit}
                className="px-3 py-1.5 text-xs font-semibold rounded bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Release {extractedEmails.length.toLocaleString()} contact{extractedEmails.length === 1 ? "" : "s"}
              </button>
            </>
          )}
          {(step === "done" || step === "error") && (
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-violet-500 text-white hover:bg-violet-600"
            >
              Close
            </button>
          )}
          {step === "pick" && (
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs font-semibold rounded border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
