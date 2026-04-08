"use client";

import { useState, useCallback, useRef, type DragEvent, type ChangeEvent } from "react";

/* ─── Constants ────────────────────────────────────────────────────────── */

const SYSTEM_FIELDS = [
  { value: "skip", label: "— Skip —", group: "action" },
  { value: "contact_id", label: "Contact ID", group: "identity" },
  { value: "first_name", label: "First Name", group: "identity" },
  { value: "last_name", label: "Last Name", group: "identity" },
  { value: "email", label: "Email", group: "identity" },
  { value: "company_website", label: "Company Website", group: "identity" },
  { value: "bucket", label: "Bucket", group: "enrichment" },
  { value: "classification", label: "Classification", group: "enrichment" },
  { value: "confidence", label: "Confidence", group: "enrichment" },
  { value: "reasoning", label: "Reasoning", group: "enrichment" },
  { value: "cost", label: "Cost", group: "enrichment" },
  { value: "status", label: "Status", group: "enrichment" },
  { value: "lead_list_name", label: "Lead List Name", group: "source" },
  { value: "segment_name", label: "Segment Name", group: "source" },
  { value: "created_date", label: "Created Date", group: "source" },
  { value: "industry", label: "Industry", group: "source" },
  { value: "employee_range", label: "Employee Range", group: "source" },
  { value: "country", label: "Country", group: "source" },
  { value: "database_provider", label: "Database Provider", group: "source" },
  { value: "scraper", label: "Scraper", group: "source" },
];

const AUTO_MAP: Record<string, string> = {
  contact_id: "contact_id",
  first_name: "first_name",
  last_name: "last_name",
  email: "email",
  company_website: "company_website",
  bucket: "bucket",
  classification: "classification",
  confidence: "confidence",
  reasoning: "reasoning",
  cost: "cost",
  status: "status",
  proxy_used: "skip",
  lead_list_name: "lead_list_name",
  "list build - segment name": "segment_name",
  "list build - created date": "created_date",
  "list build - industry": "industry",
  "list build - employee range": "employee_range",
  "list build - country": "country",
  "list build - database provider": "database_provider",
  scraper: "scraper",
};

/* Mock upload history */
const MOCK_HISTORY = [
  { id: 1, fileName: "wealth-mgmt-5-50-us.csv", date: "Apr 5, 2026", contacts: 36420, buckets: 12, status: "complete" as const },
  { id: 2, fileName: "agency-25-50-us.csv", date: "Mar 28, 2026", contacts: 28100, buckets: 8, status: "complete" as const },
  { id: 3, fileName: "saas-10-25-us-uk.csv", date: "Mar 21, 2026", contacts: 45200, buckets: 15, status: "complete" as const },
];

/* ─── CSV parsing ──────────────────────────────────────────────────────── */

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

function parseCSV(text: string) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  const headers = parseCSVLine(lines[0]);
  const rows = lines.slice(1, 6).map(parseCSVLine); // first 5 rows for preview
  const allRows = lines.slice(1).map(parseCSVLine);
  return { headers, previewRows: rows, allRows };
}

function autoMapHeader(header: string): string {
  const h = header.toLowerCase().trim();
  return AUTO_MAP[h] ?? "skip";
}

/* ─── Types ────────────────────────────────────────────────────────────── */

interface BucketSummary {
  name: string;
  count: number;
  countries: string[];
  empRanges: string[];
  avgConfidence: number;
}

type Step = "idle" | "mapping" | "importing" | "summary";

/* ─── Component ────────────────────────────────────────────────────────── */

export function UploadPage() {
  const [step, setStep] = useState<Step>("idle");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Mapping state
  const [fileName, setFileName] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [allRows, setAllRows] = useState<string[][]>([]);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [customFields, setCustomFields] = useState<string[]>([]);
  const [newFieldName, setNewFieldName] = useState("");
  const [showNewField, setShowNewField] = useState(false);

  // Summary state
  const [bucketSummary, setBucketSummary] = useState<BucketSummary[]>([]);
  const [totalContacts, setTotalContacts] = useState(0);

  /* ── File handling ────────────────────────────────────────────────── */

  const handleFile = useCallback((file: File) => {
    if (!file.name.endsWith(".csv")) return;
    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const { headers: h, previewRows: pr, allRows: ar } = parseCSV(text);
      setHeaders(h);
      setPreviewRows(pr);
      setAllRows(ar);

      // Auto-map
      const autoMappings: Record<string, string> = {};
      h.forEach((header) => {
        autoMappings[header] = autoMapHeader(header);
      });
      setMappings(autoMappings);
      setStep("mapping");
    };
    reader.readAsText(file);
  }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onFileSelect = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  /* ── Import ────────────────────────────────────────────────────────── */

  const handleImport = useCallback(() => {
    setStep("importing");

    // Find bucket column index
    const bucketHeader = Object.entries(mappings).find(([, val]) => val === "bucket")?.[0];
    const bucketIdx = bucketHeader ? headers.indexOf(bucketHeader) : -1;

    // Find country column
    const countryHeader = Object.entries(mappings).find(([, val]) => val === "country")?.[0];
    const countryIdx = countryHeader ? headers.indexOf(countryHeader) : -1;

    // Find employee range column
    const empHeader = Object.entries(mappings).find(([, val]) => val === "employee_range")?.[0];
    const empIdx = empHeader ? headers.indexOf(empHeader) : -1;

    // Find confidence column
    const confHeader = Object.entries(mappings).find(([, val]) => val === "confidence")?.[0];
    const confIdx = confHeader ? headers.indexOf(confHeader) : -1;

    // Group by bucket
    const bucketMap = new Map<string, { count: number; countries: Set<string>; empRanges: Set<string>; confSum: number }>();

    allRows.forEach((row) => {
      const bucket = bucketIdx >= 0 ? row[bucketIdx] || "Unknown" : "Unknown";
      const country = countryIdx >= 0 ? row[countryIdx] || "—" : "—";
      const emp = empIdx >= 0 ? row[empIdx] || "—" : "—";
      const conf = confIdx >= 0 ? parseFloat(row[confIdx]) || 0 : 0;

      if (!bucketMap.has(bucket)) {
        bucketMap.set(bucket, { count: 0, countries: new Set(), empRanges: new Set(), confSum: 0 });
      }
      const b = bucketMap.get(bucket)!;
      b.count++;
      b.countries.add(country);
      b.empRanges.add(emp);
      b.confSum += conf;
    });

    const summaries: BucketSummary[] = Array.from(bucketMap.entries())
      .map(([name, data]) => ({
        name,
        count: data.count,
        countries: Array.from(data.countries).slice(0, 3),
        empRanges: Array.from(data.empRanges),
        avgConfidence: data.count > 0 ? Math.round((data.confSum / data.count) * 10) / 10 : 0,
      }))
      .sort((a, b) => b.count - a.count);

    // Save to localStorage for planning page
    const existingContacts = JSON.parse(localStorage.getItem("competeiq:contacts") || "[]");
    const uploadRecord = {
      id: Date.now().toString(),
      fileName,
      date: new Date().toISOString(),
      totalContacts: allRows.length,
      buckets: summaries,
    };
    const uploads = JSON.parse(localStorage.getItem("competeiq:uploads") || "[]");
    uploads.unshift(uploadRecord);
    localStorage.setItem("competeiq:uploads", JSON.stringify(uploads));

    // Store bucket totals (merge with existing)
    const existingBuckets: Record<string, number> = JSON.parse(localStorage.getItem("competeiq:bucketTotals") || "{}");
    summaries.forEach((b) => {
      existingBuckets[b.name] = (existingBuckets[b.name] || 0) + b.count;
    });
    localStorage.setItem("competeiq:bucketTotals", JSON.stringify(existingBuckets));

    setTimeout(() => {
      setBucketSummary(summaries);
      setTotalContacts(allRows.length);
      setStep("summary");
    }, 800);
  }, [mappings, headers, allRows, fileName]);

  /* ── Mapping change ────────────────────────────────────────────────── */

  const updateMapping = (header: string, value: string) => {
    setMappings((prev) => ({ ...prev, [header]: value }));
  };

  const addCustomField = () => {
    if (newFieldName.trim() && !customFields.includes(newFieldName.trim())) {
      setCustomFields((prev) => [...prev, newFieldName.trim()]);
      setNewFieldName("");
      setShowNewField(false);
    }
  };

  /* ── Render ────────────────────────────────────────────────────────── */

  return (
    <main className="max-w-6xl mx-auto px-6 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">List Upload</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Import enrichment CSV exports to build your lead segments.
        </p>
      </div>

      {/* ── STEP: IDLE ─────────────────────────────────────────────── */}
      {step === "idle" && (
        <>
          {/* Upload zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`relative border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all duration-200 ${
              dragOver
                ? "border-violet-500 bg-violet-500/5"
                : "border-zinc-700/60 hover:border-zinc-600 bg-zinc-900/40 hover:bg-zinc-900/60"
            }`}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              onChange={onFileSelect}
              className="hidden"
            />
            <div className="flex flex-col items-center gap-3">
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors ${
                dragOver ? "bg-violet-500/20" : "bg-zinc-800"
              }`}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-zinc-400">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-200">
                  Drop your CSV file here, or <span className="text-violet-400">browse</span>
                </p>
                <p className="text-xs text-zinc-500 mt-1">Supports enrichment exports with contact + bucket data</p>
              </div>
            </div>
          </div>

          {/* Upload history */}
          <div className="mt-10">
            <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">Upload History</h2>
            <div className="rounded-xl border border-zinc-800/60 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-zinc-900/60">
                    <th className="text-left px-4 py-3 text-zinc-400 font-medium">File</th>
                    <th className="text-left px-4 py-3 text-zinc-400 font-medium">Date</th>
                    <th className="text-right px-4 py-3 text-zinc-400 font-medium">Contacts</th>
                    <th className="text-right px-4 py-3 text-zinc-400 font-medium">Buckets</th>
                    <th className="text-center px-4 py-3 text-zinc-400 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40">
                  {MOCK_HISTORY.map((h) => (
                    <tr key={h.id} className="hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-3 text-zinc-200 font-medium">{h.fileName}</td>
                      <td className="px-4 py-3 text-zinc-400">{h.date}</td>
                      <td className="px-4 py-3 text-right text-zinc-200 font-mono">{h.contacts.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-zinc-200 font-mono">{h.buckets}</td>
                      <td className="px-4 py-3 text-center">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          Complete
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── STEP: MAPPING ──────────────────────────────────────────── */}
      {step === "mapping" && (
        <>
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setStep("idle")}
                className="p-1.5 rounded-md hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 19l-7-7 7-7"/>
                </svg>
              </button>
              <div>
                <h2 className="text-lg font-semibold text-zinc-100">Map Columns</h2>
                <p className="text-xs text-zinc-500">{fileName} · {allRows.length.toLocaleString()} rows · {headers.length} columns</p>
              </div>
            </div>
            <button
              onClick={handleImport}
              className="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Import {allRows.length.toLocaleString()} contacts
            </button>
          </div>

          {/* Mapping grid */}
          <div className="rounded-xl border border-zinc-800/60 overflow-hidden mb-6">
            <div className="bg-zinc-900/60 px-4 py-3 flex items-center justify-between border-b border-zinc-800/40">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Column Mapping</span>
              <button
                onClick={() => setShowNewField(true)}
                className="text-xs text-violet-400 hover:text-violet-300 font-medium transition-colors"
              >
                + Create New Field
              </button>
            </div>

            {/* New field modal */}
            {showNewField && (
              <div className="px-4 py-3 bg-violet-500/5 border-b border-violet-500/20 flex items-center gap-3">
                <input
                  value={newFieldName}
                  onChange={(e) => setNewFieldName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addCustomField()}
                  placeholder="Field name (e.g. Lead Source)"
                  className="flex-1 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                  autoFocus
                />
                <button
                  onClick={addCustomField}
                  className="px-3 py-1.5 bg-violet-600 text-white text-xs font-medium rounded-md hover:bg-violet-500 transition-colors"
                >
                  Add
                </button>
                <button
                  onClick={() => { setShowNewField(false); setNewFieldName(""); }}
                  className="text-zinc-400 hover:text-zinc-200 text-xs transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}

            <div className="divide-y divide-zinc-800/30">
              {headers.map((header, i) => {
                const mapped = mappings[header] || "skip";
                const isAutoMapped = autoMapHeader(header) !== "skip" && mapped !== "skip";
                return (
                  <div key={header} className="flex items-center gap-4 px-4 py-2.5 hover:bg-zinc-800/20 transition-colors">
                    {/* CSV column name */}
                    <div className="w-[280px] shrink-0">
                      <span className="text-sm text-zinc-200 font-medium">{header}</span>
                      {previewRows[0] && previewRows[0][i] && (
                        <p className="text-xs text-zinc-500 mt-0.5 truncate max-w-[260px]">
                          e.g. &quot;{previewRows[0][i]}&quot;
                        </p>
                      )}
                    </div>

                    {/* Arrow */}
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-zinc-600 shrink-0">
                      <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>

                    {/* Mapping dropdown */}
                    <div className="flex items-center gap-2 flex-1">
                      <select
                        value={mapped}
                        onChange={(e) => updateMapping(header, e.target.value)}
                        className={`w-[240px] bg-zinc-800 border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500 transition-colors ${
                          mapped === "skip"
                            ? "border-zinc-700/60 text-zinc-400"
                            : "border-violet-500/40 text-zinc-200"
                        }`}
                      >
                        <optgroup label="Action">
                          <option value="skip">— Skip —</option>
                        </optgroup>
                        <optgroup label="Identity">
                          {SYSTEM_FIELDS.filter((f) => f.group === "identity").map((f) => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Enrichment">
                          {SYSTEM_FIELDS.filter((f) => f.group === "enrichment").map((f) => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                          ))}
                        </optgroup>
                        <optgroup label="Source Metadata">
                          {SYSTEM_FIELDS.filter((f) => f.group === "source").map((f) => (
                            <option key={f.value} value={f.value}>{f.label}</option>
                          ))}
                        </optgroup>
                        {customFields.length > 0 && (
                          <optgroup label="Custom Fields">
                            {customFields.map((f) => (
                              <option key={`custom_${f}`} value={`custom_${f}`}>{f}</option>
                            ))}
                          </optgroup>
                        )}
                      </select>

                      {isAutoMapped && (
                        <span className="text-[10px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-full whitespace-nowrap">
                          Auto-mapped
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Preview */}
          <div className="rounded-xl border border-zinc-800/60 overflow-hidden">
            <div className="bg-zinc-900/60 px-4 py-3 border-b border-zinc-800/40">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Data Preview (first 5 rows)</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-zinc-900/40">
                    {headers.map((h) => (
                      <th key={h} className="text-left px-3 py-2 text-zinc-500 font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/30">
                  {previewRows.map((row, ri) => (
                    <tr key={ri} className="hover:bg-zinc-800/20">
                      {row.map((cell, ci) => (
                        <td key={ci} className="px-3 py-2 text-zinc-400 whitespace-nowrap max-w-[200px] truncate">{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ── STEP: IMPORTING ────────────────────────────────────────── */}
      {step === "importing" && (
        <div className="flex flex-col items-center justify-center py-24">
          <div className="w-12 h-12 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-sm text-zinc-300">Importing {allRows.length.toLocaleString()} contacts...</p>
          <p className="text-xs text-zinc-500 mt-1">Parsing buckets and metadata</p>
        </div>
      )}

      {/* ── STEP: SUMMARY ──────────────────────────────────────────── */}
      {step === "summary" && (
        <>
          {/* Success card */}
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6 mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="text-emerald-400">
                  <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-zinc-100">Import Complete</h2>
                <p className="text-sm text-zinc-400">{fileName} · {totalContacts.toLocaleString()} contacts across {bucketSummary.length} buckets</p>
              </div>
            </div>
          </div>

          {/* Bucket breakdown */}
          <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">Buckets Found</h3>
          <div className="rounded-xl border border-zinc-800/60 overflow-hidden mb-8">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-zinc-900/60">
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">Bucket</th>
                  <th className="text-right px-4 py-3 text-zinc-400 font-medium">This Upload</th>
                  <th className="text-right px-4 py-3 text-zinc-400 font-medium">Total in DB</th>
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">Countries</th>
                  <th className="text-right px-4 py-3 text-zinc-400 font-medium">Avg Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40">
                {bucketSummary.map((b) => {
                  const dbTotal = JSON.parse(localStorage.getItem("competeiq:bucketTotals") || "{}");
                  return (
                    <tr key={b.name} className="hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-3">
                        <span className="text-zinc-200 font-medium">{b.name}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-zinc-200">{b.count.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-mono text-violet-400">{(dbTotal[b.name] || b.count).toLocaleString()}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1 flex-wrap">
                          {b.countries.map((c) => (
                            <span key={c} className="px-1.5 py-0.5 text-xs bg-zinc-800 text-zinc-400 rounded">{c}</span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono ${b.avgConfidence >= 8 ? "text-emerald-400" : b.avgConfidence >= 6 ? "text-amber-400" : "text-red-400"}`}>
                          {b.avgConfidence}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={() => {
                setStep("idle");
                setHeaders([]);
                setPreviewRows([]);
                setAllRows([]);
                setMappings({});
                setBucketSummary([]);
              }}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-700/60 rounded-lg hover:bg-zinc-800/50 transition-colors"
            >
              Upload Another
            </button>
            <a
              href="/planning"
              className="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors inline-flex items-center gap-2"
            >
              Go to Planning
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </a>
          </div>
        </>
      )}
    </main>
  );
}
