const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

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
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${API_TOKEN}`,
    },
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
