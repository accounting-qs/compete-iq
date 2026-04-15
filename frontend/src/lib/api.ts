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
    bucket_id: string;
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
  data: Partial<{ title_copy_id: string; desc_copy_id: string; accounts_used: number; volume: number; remaining: number; list_url: string; gcal_invited: number }>
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

/* ── Outreach: Uploads ─────────────────────────────────────────────────── */

export async function fetchUploads(): Promise<{ uploads: ApiUpload[] }> {
  const res = await fetch(`${API_URL}/outreach/uploads`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch uploads");
  return res.json();
}

export async function uploadCsvFile(file: File): Promise<UploadFileResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}/outreach/uploads/file`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to upload CSV: ${text}`);
  }
  return res.json();
}

export async function startImport(
  uploadId: string,
  fieldMappings: Record<string, string>,
  duplicateMode: string = "ignore",
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/outreach/uploads/${uploadId}/import`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ field_mappings: fieldMappings, duplicate_mode: duplicateMode }),
  });
  if (!res.ok) throw new Error("Failed to start import");
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
