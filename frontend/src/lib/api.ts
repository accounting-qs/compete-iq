const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${API_TOKEN}` };
}

function jsonHeaders(): Record<string, string> {
  return { ...authHeaders(), "Content-Type": "application/json" };
}

/* ── Calendar Blocker ──────────────────────────────────────────────────── */

export interface CalendarVariant {
  variant: "A" | "B" | "C";
  style: string;
  title: string;
  description: string;
}

export interface GenerateCalendarRequest {
  segment: string;
  sub_niche?: string;
  topic?: string;
  client_story?: string;
}

export interface GenerateCalendarResponse {
  variants: CalendarVariant[];
}

export async function generateCalendarBlocker(
  req: GenerateCalendarRequest
): Promise<GenerateCalendarResponse> {
  const res = await fetch(`${API_URL}/generate/calendar-event`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("Rate limit hit — wait a moment and try again.");
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Generation failed");
  }

  return res.json();
}

/* ── Outreach: Types ───────────────────────────────────────────────────── */

export interface ApiBucket {
  id: string;
  name: string;
  industry: string | null;
  total_contacts: number;
  remaining_contacts: number;
  countries: string[];
  emp_range: string | null;
  source_file: string | null;
  copies_count: { titles: number; descriptions: number };
  has_primary_title: boolean;
  has_primary_description: boolean;
  title_primary_picked: boolean;
  desc_primary_picked: boolean;
  created_at: string | null;
  // included when ?include=copies
  titles?: ApiCopy[];
  descriptions?: ApiCopy[];
}

export interface ApiCopy {
  id: string;
  bucket_id: string;
  copy_type: "title" | "description";
  variant_index: number;
  text: string;
  is_primary: boolean;
  ai_feedback: string | null;
  created_at: string | null;
  is_assigned?: boolean;
}

export interface ApiSender {
  id: string;
  name: string;
  total_accounts: number;
  send_per_account: number;
  days_per_webinar: number;
  color: string | null;
  display_order: number;
  is_active: boolean;
}

export interface ApiWebinar {
  id: string;
  number: number;
  date: string;
  status: string;
  broadcast_id: string | null;
  main_title: string | null;
  registration_link: string | null;
  unsubscribe_link: string | null;
  assignment_count: number;
  total_volume: number;
  total_remaining: number;
  total_accounts: number;
}

export interface ApiAssignment {
  id: string;
  webinar_id: string;
  bucket: { id: string; name: string; industry: string | null } | null;
  sender: { id: string; name: string; color: string | null } | null;
  description: string | null;
  list_url: string | null;
  volume: number;
  remaining: number;
  gcal_invited: number;
  accounts_used: number;
  send_per_account: number | null;
  days: number | null;
  title_copy: ApiCopy | null;
  desc_copy: ApiCopy | null;
  countries_override: string | null;
  emp_range_override: string | null;
  is_nonjoiners: boolean;
  is_no_list_data: boolean;
  is_setup: boolean;
  source_type: string;
  source_upload_id: string | null;
  list_name: string | null;
  display_order: number;
  bucket_remaining?: number;
}

export interface ApiUpload {
  id: string;
  file_name: string;
  total_contacts: number;
  total_buckets: number;
  bucket_summary: Array<{ name: string; count: number; countries: string[]; empRanges: string[]; avgConfidence: number }> | null;
  status: string;
  progress: number;
  processed_rows: number;
  inserted_count: number;
  skipped_count: number;
  overwritten_count: number;
  error_message: string | null;
  created_at: string | null;
}

export interface UploadFileResponse {
  id: string;
  file_name: string;
  storage_path: string;
  total_rows: number;
  file_size: number;
  headers: string[];
  preview_rows: string[][];
}

export interface UploadStatusResponse {
  id: string;
  file_name: string;
  status: string;
  progress: number;
  total_rows: number;
  processed_rows: number;
  inserted_count: number;
  skipped_count: number;
  overwritten_count: number;
  error_message: string | null;
  bucket_summary: Array<{ name: string; count: number; countries: string[]; empRanges: string[]; avgConfidence: number }> | null;
}

/* ── Outreach: Buckets ─────────────────────────────────────────────────── */

export async function fetchBuckets(includeCopies = false): Promise<{ buckets: ApiBucket[] }> {
  const params = includeCopies ? "?include=copies" : "";
  const res = await fetch(`${API_URL}/outreach/buckets${params}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch buckets");
  return res.json();
}

export async function createBucket(data: {
  name: string;
  industry?: string;
  total_contacts: number;
  remaining_contacts?: number;
  countries?: string[];
  emp_range?: string;
  source_file?: string;
}): Promise<ApiBucket> {
  const res = await fetch(`${API_URL}/outreach/buckets`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create bucket");
  return res.json();
}

export async function updateBucket(
  bucketId: string,
  data: Partial<{ name: string; industry: string; total_contacts: number; remaining_contacts: number; countries: string[]; emp_range: string }>
): Promise<ApiBucket> {
  const res = await fetch(`${API_URL}/outreach/buckets/${bucketId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update bucket");
  return res.json();
}

/* ── Outreach: Copies ──────────────────────────────────────────────────── */

export async function fetchBucketCopies(bucketId: string): Promise<{ bucket_id: string; titles: ApiCopy[]; descriptions: ApiCopy[] }> {
  const res = await fetch(`${API_URL}/outreach/buckets/${bucketId}/copies`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch copies");
  return res.json();
}

export async function generateCopies(
  bucketId: string,
  data: { copy_type: "title" | "description" | "both"; variant_count?: number }
): Promise<{ bucket_id: string; batch_id: string; titles: ApiCopy[]; descriptions: ApiCopy[] }> {
  const res = await fetch(`${API_URL}/outreach/buckets/${bucketId}/copies/generate`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to generate copies");
  return res.json();
}

/* ── Bulk (background) copy generation ─────────────────────────────────── */

export type CopyGenJobStatus = "pending" | "generating" | "done" | "failed";

export interface ApiCopyGenJob {
  id: string;
  bucket_id: string;
  copy_type: "title" | "description";
  status: CopyGenJobStatus;
  error_message?: string | null;
  variant_count?: number;
  created_at?: string | null;
  completed_at?: string | null;
}

export async function generateCopiesBulk(data: {
  bucket_ids: string[];
  copy_type: "title" | "description" | "both";
  variant_count?: number;
}): Promise<{ jobs: ApiCopyGenJob[] }> {
  const res = await fetch(`${API_URL}/outreach/buckets/copies/generate-bulk`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to start bulk generation");
  return res.json();
}

export async function fetchCopyGenerationStatus(): Promise<{ jobs: ApiCopyGenJob[] }> {
  const res = await fetch(`${API_URL}/outreach/buckets/copies/generation-status`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch generation status");
  return res.json();
}

export async function retryCopyGenerationJob(jobId: string): Promise<ApiCopyGenJob> {
  const res = await fetch(`${API_URL}/outreach/buckets/copies/generation-jobs/${jobId}/retry`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to retry generation job");
  return res.json();
}

/* ── Bucket merge ──────────────────────────────────────────────────────── */

export interface MergeBlockingBucket {
  id: string;
  name: string;
  assignment_count: number;
}

export interface MergeBucketsResult {
  keeper_bucket_id: string;
  keeper_name: string;
  contacts_moved: number;
  merged_bucket_ids: string[];
  merged_bucket_count: number;
  keeper_total_contacts: number;
  keeper_remaining_contacts: number;
}

export class MergeBlockedError extends Error {
  blocking: MergeBlockingBucket[];
  constructor(message: string, blocking: MergeBlockingBucket[]) {
    super(message);
    this.blocking = blocking;
    this.name = "MergeBlockedError";
  }
}

export async function mergeBuckets(data: {
  keeper_bucket_id: string;
  source_bucket_ids: string[];
}): Promise<MergeBucketsResult> {
  const res = await fetch(`${API_URL}/outreach/buckets/merge`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (res.status === 409) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail ?? {};
    throw new MergeBlockedError(
      detail.message || "Merge blocked by existing assignments",
      Array.isArray(detail.blocking_buckets) ? detail.blocking_buckets : []
    );
  }
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to merge buckets"));
  return res.json();
}

export async function updateCopy(
  copyId: string,
  data: { text?: string; is_primary?: boolean }
): Promise<ApiCopy> {
  const res = await fetch(`${API_URL}/outreach/copies/${copyId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update copy");
  return res.json();
}

export async function createCopy(
  bucketId: string,
  data: { copy_type: "title" | "description"; text?: string }
): Promise<ApiCopy> {
  const res = await fetch(`${API_URL}/outreach/buckets/${bucketId}/copies`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create copy");
  return res.json();
}

export async function regenerateCopy(
  copyId: string,
  feedback: string
): Promise<ApiCopy> {
  const res = await fetch(`${API_URL}/outreach/copies/${copyId}/regenerate`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ feedback }),
  });
  if (!res.ok) throw new Error("Failed to regenerate copy");
  return res.json();
}

export async function deleteCopy(copyId: string): Promise<void> {
  const res = await fetch(`${API_URL}/outreach/copies/${copyId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete copy");
}

/* ── Outreach: Senders ─────────────────────────────────────────────────── */

export async function fetchSenders(): Promise<{ senders: ApiSender[] }> {
  const res = await fetch(`${API_URL}/outreach/senders`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch senders");
  return res.json();
}

export async function createSender(data: {
  name: string;
  total_accounts?: number;
  send_per_account?: number;
  days_per_webinar?: number;
  color?: string;
}): Promise<ApiSender> {
  const res = await fetch(`${API_URL}/outreach/senders`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create sender");
  return res.json();
}

export async function updateSender(
  senderId: string,
  data: Partial<{ name: string; total_accounts: number; send_per_account: number; days_per_webinar: number; color: string; is_active: boolean }>
): Promise<ApiSender> {
  const res = await fetch(`${API_URL}/outreach/senders/${senderId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update sender");
  return res.json();
}

/* ── Outreach: Webinars ────────────────────────────────────────────────── */

export async function fetchWebinars(): Promise<{ webinars: ApiWebinar[] }> {
  const res = await fetch(`${API_URL}/outreach/webinars`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch webinars");
  return res.json();
}

export async function createWebinar(data: { number: number; date: string }): Promise<ApiWebinar> {
  const res = await fetch(`${API_URL}/outreach/webinars`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to create webinar");
  }
  return res.json();
}

export async function updateWebinar(
  webinarId: string,
  data: Partial<{ number: number; date: string; status: string; broadcast_id: string; main_title: string; registration_link: string; unsubscribe_link: string }>
): Promise<ApiWebinar> {
  const res = await fetch(`${API_URL}/outreach/webinars/${webinarId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update webinar");
  return res.json();
}

export async function deleteWebinar(webinarId: string): Promise<{ deleted: boolean; released: number }> {
  const res = await fetch(`${API_URL}/outreach/webinars/${webinarId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete webinar");
  return res.json();
}

/* ── Outreach: Assignments ─────────────────────────────────────────────── */

export async function fetchWebinarLists(webinarId: string): Promise<{ assignments: ApiAssignment[] }> {
  const res = await fetch(`${API_URL}/outreach/webinars/${webinarId}/lists`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch assignments");
  return res.json();
}

export async function assignBucketToWebinar(
  webinarId: string,
  data: {
    bucket_id?: string;
    upload_id?: string;
    sender_id: string;
    volume: number;
    accounts_used?: number;
    send_per_account?: number;
    days?: number;
    countries_override?: string;
    emp_range_override?: string;
  }
): Promise<ApiAssignment> {
  const res = await fetch(`${API_URL}/outreach/webinars/${webinarId}/assign`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to assign");
  }
  return res.json();
}

export async function updateAssignment(
  assignmentId: string,
  data: Partial<{ title_copy_id: string; desc_copy_id: string; accounts_used: number; volume: number; remaining: number; list_url: string; list_name: string; gcal_invited: number; is_setup: boolean }>
): Promise<ApiAssignment> {
  const res = await fetch(`${API_URL}/outreach/assignments/${assignmentId}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update assignment");
  return res.json();
}

export async function deleteAssignment(assignmentId: string): Promise<{ released: number; bucket_id: string | null; bucket_remaining: number | null }> {
  const res = await fetch(`${API_URL}/outreach/assignments/${assignmentId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete assignment");
  return res.json();
}

/* ── Outreach: Custom Lists ────────────────────────────────────────────── */

export interface ApiCustomList {
  id: string;
  name: string;
  total_contacts: number;
  available_contacts: number;
  created_at: string | null;
}

export async function fetchCustomLists(): Promise<{ lists: ApiCustomList[] }> {
  const res = await fetch(`${API_URL}/outreach/uploads/custom-lists`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch custom lists");
  return res.json();
}

export async function fetchCustomListCopies(uploadId: string): Promise<{ upload_id: string; titles: ApiCopy[]; descriptions: ApiCopy[] }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/copies`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch custom list copies");
  return res.json();
}

export async function createCustomListCopy(
  uploadId: string,
  data: { copy_type: "title" | "description"; text: string }
): Promise<ApiCopy> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/copies`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create custom list copy");
  return res.json();
}

export async function generateCustomListCopies(
  uploadId: string,
  data: { copy_type: "title" | "description" | "both"; variant_count?: number }
): Promise<{ upload_id: string; batch_id: string; titles: ApiCopy[]; descriptions: ApiCopy[] }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/copies/generate`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to generate custom list copies");
  return res.json();
}

/* ── Outreach: Uploads ─────────────────────────────────────────────────── */

export async function fetchUploads(): Promise<{ uploads: ApiUpload[] }> {
  const res = await fetch(`${API_URL}/outreach/uploads`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch uploads");
  return res.json();
}

/* ── Direct-to-Supabase Upload ────────────────────────────────────────── */

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  const text = await res.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    /* non-JSON error body */
  }
  return text;
}

export async function requestSignedUploadUrl(filename: string, fileSize: number): Promise<{
  upload_id: string;
  signed_url: string;
  storage_path: string;
}> {
  const res = await fetch(`${API_URL}/outreach/uploads/presign`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ filename, file_size: fileSize }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to get signed URL"));
  }
  return res.json();
}

export function uploadToStorage(
  signedUrl: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signedUrl, true);
    xhr.setRequestHeader("Content-Type", "text/csv");
    xhr.setRequestHeader("x-upsert", "true");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Storage upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    };

    xhr.onerror = () => reject(new Error("Storage upload network error"));
    xhr.ontimeout = () => reject(new Error("Storage upload timed out"));
    // Dynamic timeout: 3s per MB, minimum 10 minutes
    xhr.timeout = Math.max(600000, (file.size / (1024 * 1024)) * 3000);

    xhr.send(file);
  });
}

export async function confirmUpload(
  uploadId: string,
  fileSize: number,
): Promise<UploadFileResponse> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/confirm`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ file_size: fileSize }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to confirm upload"));
  }
  return res.json();
}

export async function startImport(
  uploadId: string,
  fieldMappings: Record<string, string>,
  duplicateMode: string = "ignore",
  uploadMode: string = "bucket",
  customListName?: string,
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/import`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      field_mappings: fieldMappings,
      duplicate_mode: duplicateMode,
      upload_mode: uploadMode,
      custom_list_name: customListName,
    }),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to start import"));
  return res.json();
}

export async function fetchUploadStatus(uploadId: string): Promise<UploadStatusResponse> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/status`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch upload status");
  return res.json();
}

export async function fetchUploadHeaders(uploadId: string): Promise<UploadFileResponse> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/headers`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch upload headers");
  return res.json();
}

export async function deleteUpload(uploadId: string): Promise<{ id: string; deleted_contacts: number; message: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }
  return res.json();
}

export async function pauseImport(uploadId: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/pause`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to pause import");
  return res.json();
}

export async function resumeImport(uploadId: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/resume`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to resume import");
  return res.json();
}

export async function cancelImport(uploadId: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to cancel import");
  return res.json();
}

/* ── Outreach: Custom Fields ───────────────────────────────────────────── */

export interface ApiCustomField {
  id: string;
  field_name: string;
  field_type: string;
  display_order: number;
}

export async function fetchCustomFields(): Promise<{ fields: ApiCustomField[] }> {
  const res = await fetch(`${API_URL}/outreach/custom-fields`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch custom fields");
  return res.json();
}

export async function createCustomField(data: {
  field_name: string;
  field_type?: string;
}): Promise<ApiCustomField> {
  const res = await fetch(`${API_URL}/outreach/custom-fields`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create custom field");
  return res.json();
}


/* ── Brain Management ────────────────────────────────────────────────────── */

export interface ApiPrinciple {
  id: string;
  principle_text: string;
  knowledge_type: string;
  category: string | null;
  is_active: boolean;
  display_order: number | null;
  times_applied: number;
  created_at: string | null;
}

export interface ApiCaseStudy {
  id: string;
  title: string;
  client_name: string | null;
  industry: string | null;
  tags: string[];
  content: string;
  is_active: boolean;
  created_at: string | null;
}

export interface ApiBrainContent {
  universal_brain: string;
  format_brain: string;
  format_brain_id: string | null;
}

// Principles
export async function fetchPrinciples(): Promise<ApiPrinciple[]> {
  const res = await fetch(`${API_URL}/outreach/brain/principles`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch principles");
  return res.json();
}

export async function createPrinciple(data: {
  principle_text: string;
  knowledge_type?: string;
  category?: string;
}): Promise<ApiPrinciple> {
  const res = await fetch(`${API_URL}/outreach/brain/principles`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create principle");
  return res.json();
}

export async function updatePrinciple(id: string, data: {
  principle_text?: string;
  category?: string;
  is_active?: boolean;
}): Promise<ApiPrinciple> {
  const res = await fetch(`${API_URL}/outreach/brain/principles/${id}`, {
    method: "PUT", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update principle");
  return res.json();
}

export async function deletePrinciple(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/outreach/brain/principles/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete principle");
}

// Case Studies
export async function fetchCaseStudies(): Promise<ApiCaseStudy[]> {
  const res = await fetch(`${API_URL}/outreach/brain/case-studies`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch case studies");
  return res.json();
}

export async function createCaseStudy(data: {
  title: string;
  client_name?: string;
  industry?: string;
  tags?: string[];
  content: string;
}): Promise<ApiCaseStudy> {
  const res = await fetch(`${API_URL}/outreach/brain/case-studies`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create case study");
  return res.json();
}

export async function updateCaseStudy(id: string, data: {
  title?: string;
  client_name?: string;
  industry?: string;
  tags?: string[];
  content?: string;
  is_active?: boolean;
}): Promise<ApiCaseStudy> {
  const res = await fetch(`${API_URL}/outreach/brain/case-studies/${id}`, {
    method: "PUT", headers: jsonHeaders(), body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update case study");
  return res.json();
}

export async function deleteCaseStudy(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/outreach/brain/case-studies/${id}`, {
    method: "DELETE", headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete case study");
}

// Brain Content
export async function fetchBrainContent(): Promise<ApiBrainContent> {
  const res = await fetch(`${API_URL}/outreach/brain/content`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch brain content");
  return res.json();
}

export async function updateUniversalBrain(brain_content: string): Promise<{ brain_content: string; version: number }> {
  const res = await fetch(`${API_URL}/outreach/brain/content/universal`, {
    method: "PUT", headers: jsonHeaders(), body: JSON.stringify({ brain_content }),
  });
  if (!res.ok) throw new Error("Failed to update universal brain");
  return res.json();
}

export async function updateFormatBrain(brain_content: string): Promise<{ brain_content: string }> {
  const res = await fetch(`${API_URL}/outreach/brain/content/format`, {
    method: "PUT", headers: jsonHeaders(), body: JSON.stringify({ brain_content }),
  });
  if (!res.ok) throw new Error("Failed to update format brain");
  return res.json();
}


/* ── Assignment Contacts ──────────────────────────────────────────────────── */

export interface ApiContact {
  id: string;
  email: string;
  first_name: string | null;
  outreach_status: "assigned" | "used";
  used_at: string | null;
}

export interface AssignmentContactsResponse {
  assignment: {
    id: string;
    bucket_name: string | null;
    list_name: string | null;
    webinar_number: number | null;
    webinar_date: string | null;
    volume: number;
  };
  contacts: ApiContact[];
  counts: { assigned: number; used: number; total: number };
}

export async function fetchAssignmentContacts(
  assignmentId: string,
  status: "assigned" | "used" | "all" = "assigned"
): Promise<AssignmentContactsResponse> {
  const res = await fetch(`${API_URL}/outreach/assignments/${assignmentId}/contacts?status=${status}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch contacts");
  return res.json();
}

export async function markContactsUsed(
  assignmentId: string,
  contactIds: string[]
): Promise<{ marked: number }> {
  const res = await fetch(`${API_URL}/outreach/assignments/${assignmentId}/contacts/mark-used`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ contact_ids: contactIds }),
  });
  if (!res.ok) throw new Error("Failed to mark contacts as used");
  return res.json();
}

/* ── Statistics ─────────────────────────────────────────────────────────── */

export interface StatisticsMetrics {
  // Raw source fields
  listSize: number | null;
  listRemain: number | null;
  gcalInvited: number | null;
  gcalInvitedGhl: number | null;
  accountsNeeded: number | null;
  invited: number | null;
  unsubscribes: number | null;
  ghlPageViews: number | null;
  lpRegs: number | null;
  yesMarked: number | null;
  yesAttended: number | null;
  yes10MinPlus: number | null;
  yesAttendBySmsClick: number | null;
  yesBookings: number | null;
  maybeMarked: number | null;
  maybeAttended: number | null;
  maybe10MinPlus: number | null;
  maybeAttendBySmsClick: number | null;
  maybeBookings: number | null;
  selfRegMarked: number | null;
  selfRegAttended: number | null;
  selfReg10MinPlus: number | null;
  selfRegBookings: number | null;
  totalRegs: number | null;
  totalAttended: number | null;
  attendBySmsReminder: number | null;
  total10MinPlus: number | null;
  total30MinPlus: number | null;
  totalBookings: number | null;
  totalCallsDatePassed: number | null;
  confirmed: number | null;
  shows: number | null;
  noShows: number | null;
  canceled: number | null;
  won: number | null;
  disqualified: number | null;
  qualified: number | null;
  leadQualityGreat: number | null;
  leadQualityOk: number | null;
  leadQualityBarelyPassable: number | null;
  leadQualityBadDq: number | null;
  avgProjectedDealSize: number | null;
  avgClosedDealValue: number | null;
  // Derived fields
  unsubPercent: number | null;
  ctrPercent: number | null;
  lpRegPercent: number | null;
  yesPer1kInv: number | null;
  yesPercent: number | null;
  yesAttendPercent: number | null;
  yesStay10MinPercent: number | null;
  yesAttendBySmsClickPercent: number | null;
  yesBookingsPer1kInv: number | null;
  maybePer1kInv: number | null;
  maybeAttendPercent: number | null;
  maybeStay10MinPercent: number | null;
  maybeAttendBySmsClickPercent: number | null;
  maybeBookingsPer1kInv: number | null;
  selfRegPer1kInv: number | null;
  selfRegAttendPercent: number | null;
  selfRegStay10MinPercent: number | null;
  selfRegBookingsPer1kInv: number | null;
  invitedToRegPercent: number | null;
  regToAttendPercent: number | null;
  invitedToAttendPercent: number | null;
  totalAttendedPer1kInv: number | null;
  attendBySmsReminderPercent: number | null;
  total10MinPlusPer1kInv: number | null;
  attend10MinPercent: number | null;
  total30MinPlusPer1kInv: number | null;
  attend30MinPercent: number | null;
  bookingsPerAttended: number | null;
  bookingsPerPast10Min: number | null;
  totalBookingsPer1kInv: number | null;
  showPercent: number | null;
  closeRatePercent: number | null;
  qualPercent: number | null;
  [key: string]: number | null;
}

export interface ApiStatisticsRow {
  id: string;
  webinarNumber: number;
  workbookRow: number;
  kind: "list" | "nonjoiners" | "no_list_data";
  status: string | null;
  note: string | null;
  listUrl: string | null;
  description: string | null;
  sendInfo: string | null;
  descLabel: string | null;
  titleText: string | null;
  segmentName: string | null;
  createdDate: string | null;
  industry: string | null;
  employeeRange: string | null;
  country: string | null;
  metrics: StatisticsMetrics;
}

export interface ApiStatisticsWebinar {
  id: string;
  number: number;
  date: string | null;
  title: string | null;
  workbookRow: number;
  source: string;
  summary: StatisticsMetrics;
  rows: ApiStatisticsRow[];
}

export interface StatisticsMeta {
  source: "ghl" | "workbook";
  last_sync: {
    run_id: string;
    sync_type: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    contacts_synced: number;
    opportunities_synced: number;
  } | null;
}

export async function fetchStatisticsWebinars(source: "auto" | "ghl" | "workbook" = "auto"): Promise<{ webinars: ApiStatisticsWebinar[]; meta: StatisticsMeta }> {
  const res = await fetch(`${API_URL}/statistics/webinars?source=${source}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch statistics");
  return res.json();
}

/* ── GHL Sync ───────────────────────────────────────────────────────────── */

export interface GhlSyncRun {
  id: string;
  sync_type: "full" | "incremental";
  trigger: "scheduled" | "manual";
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  contacts_synced: number;
  opportunities_synced: number;
  errors_count: number;
  error_details: unknown[] | null;
}

export interface GhlSyncStatus {
  latest: GhlSyncRun | null;
  is_running: boolean;
}

export interface GhlSyncSettings {
  incremental_enabled: boolean;
  incremental_interval_hours: number;
  weekly_full_enabled: boolean;
  weekly_full_day_of_week: string;
  weekly_full_hour_local: number;
  weekly_full_timezone: string;
  updated_at: string | null;
}

export async function fetchGhlSyncStatus(): Promise<GhlSyncStatus> {
  const res = await fetch(`${API_URL}/ghl-sync/status`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch sync status");
  return res.json();
}

export async function fetchGhlSyncHistory(limit = 50): Promise<{ runs: GhlSyncRun[] }> {
  const res = await fetch(`${API_URL}/ghl-sync/history?limit=${limit}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch sync history");
  return res.json();
}

export async function triggerGhlSync(syncType: "full" | "incremental"): Promise<{ run_id: string; sync_type: string; status: string }> {
  const res = await fetch(`${API_URL}/ghl-sync/trigger?sync_type=${syncType}`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to trigger sync");
  }
  return res.json();
}

export async function fetchGhlSyncSettings(): Promise<GhlSyncSettings> {
  const res = await fetch(`${API_URL}/ghl-sync/settings`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch sync settings");
  return res.json();
}

export async function updateGhlSyncSettings(payload: Partial<GhlSyncSettings>): Promise<GhlSyncSettings> {
  const res = await fetch(`${API_URL}/ghl-sync/settings`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to update settings");
  }
  return res.json();
}

/* ── Connectors: WebinarGeek ───────────────────────────────────────────── */

export interface WgCredentialStatus {
  configured: boolean;
  api_key_masked?: string | null;
}

export interface WgWebinar {
  broadcast_id: string;
  name: string;
  internal_title: string | null;
  starts_at: string | null;
  duration_seconds: number | null;
  subscriptions_count: number;
  live_viewers_count: number;
  replay_viewers_count: number;
  has_ended: boolean;
  cancelled: boolean;
  last_synced_at: string | null;
  synced_subscriber_count: number;
}

export interface WgSubscriber {
  id: string;
  broadcast_id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  registration_source: string | null;
  subscribed_at: string | null;
  watched_live: boolean | null;
  watched_replay: boolean | null;
  minutes_viewing: number | null;
  viewing_device: string | null;
  viewing_country: string | null;
}

export async function fetchWgStatus(): Promise<WgCredentialStatus> {
  const res = await fetch(`${API_URL}/connectors/webinargeek`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch WebinarGeek status");
  return res.json();
}

export async function saveWgApiKey(api_key: string): Promise<WgCredentialStatus> {
  const res = await fetch(`${API_URL}/connectors/webinargeek`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ api_key }),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to save API key"));
  return res.json();
}

export async function deleteWgApiKey(): Promise<void> {
  const res = await fetch(`${API_URL}/connectors/webinargeek`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete API key");
}

export async function fetchWgWebinars(opts?: { limit?: number; offset?: number; q?: string }): Promise<{ broadcasts: WgWebinar[]; total: number }> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  if (opts?.q) params.set("q", opts.q);
  const res = await fetch(
    `${API_URL}/connectors/webinargeek/webinars${params.toString() ? `?${params}` : ""}`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to fetch broadcasts");
  return res.json();
}

export async function refreshWgWebinars(): Promise<{ count: number }> {
  const res = await fetch(`${API_URL}/connectors/webinargeek/webinars/refresh`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to refresh broadcasts"));
  return res.json();
}

export async function syncWgSubscribers(broadcastId: string): Promise<{
  broadcast_id: string;
  total: number;
}> {
  const res = await fetch(
    `${API_URL}/connectors/webinargeek/webinars/${encodeURIComponent(broadcastId)}/sync`,
    { method: "POST", headers: authHeaders() }
  );
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to sync subscribers"));
  return res.json();
}

export async function syncAllWgSubscribers(): Promise<{
  broadcasts_synced: number;
  total_subscribers: number;
  errors: string[];
}> {
  const res = await fetch(`${API_URL}/connectors/webinargeek/webinars/sync-all`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorDetail(res, "Failed to sync all"));
  return res.json();
}

export async function fetchWgSubscribers(opts: {
  broadcast_id?: string;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<{ subscribers: WgSubscriber[]; total: number }> {
  const params = new URLSearchParams();
  if (opts.broadcast_id) params.set("broadcast_id", opts.broadcast_id);
  if (opts.q) params.set("q", opts.q);
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  const res = await fetch(
    `${API_URL}/connectors/webinargeek/subscribers?${params}`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error("Failed to fetch subscribers");
  return res.json();
}

export function wgSubscribersCsvUrl(opts: { broadcast_id?: string; q?: string }): string {
  const params = new URLSearchParams();
  if (opts.broadcast_id) params.set("broadcast_id", opts.broadcast_id);
  if (opts.q) params.set("q", opts.q);
  return `${API_URL}/connectors/webinargeek/subscribers/export?${params}`;
}
