export type GenerationStatus = "new" | "saved" | "needs-work";
export type GenerationFormat = "calendar-blocker";

export interface StoredGeneration {
  id: string;
  format: GenerationFormat;
  audience: string;
  clientStory?: string;
  createdAt: string;
  status: GenerationStatus;
  variants: Array<{
    variant: "A" | "B" | "C";
    style: string;
    title: string;
    description: string;
  }>;
}

const STORAGE_KEY = "webinar-studio:library";

export function loadLibrary(): StoredGeneration[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveLibrary(items: StoredGeneration[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export function addGeneration(gen: Omit<StoredGeneration, "id" | "createdAt" | "status">): StoredGeneration {
  const item: StoredGeneration = {
    ...gen,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    status: "new",
  };
  const existing = loadLibrary();
  saveLibrary([item, ...existing]);
  return item;
}

export function updateGenerationStatus(id: string, status: GenerationStatus): void {
  const items = loadLibrary();
  saveLibrary(items.map(g => (g.id === id ? { ...g, status } : g)));
}

export function deleteGeneration(id: string): void {
  saveLibrary(loadLibrary().filter(g => g.id !== id));
}
