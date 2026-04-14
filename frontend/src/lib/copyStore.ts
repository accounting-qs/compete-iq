/**
 * Shared copy store — bridges Copy Generator ↔ Planning pages.
 * Uses localStorage so generated copies persist across page navigations.
 */

export interface CopyVariant {
  id: string;
  text: string;
  isPrimary: boolean;
}

export interface BucketCopies {
  bucketId: string;
  bucketName: string;
  industry: string;
  titles: CopyVariant[];
  descriptions: CopyVariant[];
  generatedAt: string;
}

const STORAGE_KEY = "webinar-studio:bucket-copies";

/** Load all bucket copies from localStorage */
export function loadBucketCopies(): Map<string, BucketCopies> {
  if (typeof window === "undefined") return new Map();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Map();
    const arr: BucketCopies[] = JSON.parse(raw);
    return new Map(arr.map((bc) => [bc.bucketId, bc]));
  } catch {
    return new Map();
  }
}

/** Save all bucket copies to localStorage */
export function saveBucketCopies(copies: Map<string, BucketCopies>): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(copies.values())));
}

/** Get copies for a specific bucket */
export function getBucketCopies(bucketId: string): BucketCopies | null {
  const all = loadBucketCopies();
  return all.get(bucketId) || null;
}

/** Get the primary title for a bucket */
export function getPrimaryTitle(bucketId: string): CopyVariant | null {
  const bc = getBucketCopies(bucketId);
  if (!bc) return null;
  return bc.titles.find((t) => t.isPrimary) || bc.titles[0] || null;
}

/** Get the primary description for a bucket */
export function getPrimaryDescription(bucketId: string): CopyVariant | null {
  const bc = getBucketCopies(bucketId);
  if (!bc) return null;
  return bc.descriptions.find((d) => d.isPrimary) || bc.descriptions[0] || null;
}

/** Upsert copies for a bucket (called from Copy Generator on generation) */
export function upsertBucketCopies(copies: BucketCopies): void {
  const all = loadBucketCopies();
  all.set(copies.bucketId, copies);
  saveBucketCopies(all);
}

/** Update a single variant's text */
export function updateVariantText(
  bucketId: string,
  type: "title" | "description",
  variantId: string,
  newText: string
): void {
  const all = loadBucketCopies();
  const bc = all.get(bucketId);
  if (!bc) return;
  const list = type === "title" ? bc.titles : bc.descriptions;
  const idx = list.findIndex((v) => v.id === variantId);
  if (idx >= 0) list[idx] = { ...list[idx], text: newText };
  saveBucketCopies(all);
}

/** Set a variant as primary */
export function setVariantPrimary(
  bucketId: string,
  type: "title" | "description",
  variantId: string
): void {
  const all = loadBucketCopies();
  const bc = all.get(bucketId);
  if (!bc) return;
  const list = type === "title" ? bc.titles : bc.descriptions;
  list.forEach((v) => (v.isPrimary = v.id === variantId));
  saveBucketCopies(all);
}

/** Add a new variant to a bucket */
export function addVariantToBucket(
  bucketId: string,
  type: "title" | "description",
  text: string
): void {
  const all = loadBucketCopies();
  const bc = all.get(bucketId);
  if (!bc) return;
  const newVariant: CopyVariant = { id: `v-${Date.now()}`, text, isPrimary: false };
  if (type === "title") bc.titles.push(newVariant);
  else bc.descriptions.push(newVariant);
  saveBucketCopies(all);
}
