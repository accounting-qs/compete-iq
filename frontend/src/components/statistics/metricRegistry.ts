export type MetricFormat = "number" | "percent" | "per1k" | "currency" | "ratio";
export type MetricGroup = "Base" | "Delivery" | "Yes" | "Maybe" | "Self Reg" | "Attendance" | "Sales" | "Quality";

export interface MetricColumn {
  key: string;
  label: string;
  group: MetricGroup;
  format: MetricFormat;
  decimals?: number;
  /** Short derivation formula for ratio/per-1k metrics, e.g. "yesMarked / invited". */
  formulaText?: string;
  /** One-sentence description of what this column tracks. */
  description?: string;
  /** Where the underlying number comes from — data source + filter explanation. */
  source?: string;
}

export const METRIC_GROUPS: MetricGroup[] = [
  "Base", "Delivery", "Yes", "Maybe", "Self Reg", "Attendance", "Sales", "Quality",
];

export const METRIC_COLUMNS: MetricColumn[] = [
  // ── Base ──
  {
    key: "listSize", label: "List Size", group: "Base", format: "number",
    description: "Number of contacts planned for this list in Campaign Planning.",
    source: "Sum of WebinarListAssignment.volume for the webinar (or the assignment on per-list rows).",
  },
  {
    key: "listRemain", label: "Remain", group: "Base", format: "number",
    description: "Planned contacts still remaining (not yet used).",
    source: "Sum of WebinarListAssignment.remaining from Planning.",
  },
  {
    key: "accountsNeeded", label: "Accts", group: "Base", format: "number", decimals: 1,
    description: "Sender accounts needed to deliver this list at the planned volume.",
    source: "Sum of WebinarListAssignment.accounts_used from Planning.",
  },
  {
    key: "gcalInvited", label: "GCal Inv", group: "Base", format: "number",
    description: "Google Calendar invite count recorded on the Planning assignment.",
    source: "Sum of WebinarListAssignment.gcal_invited (manually entered in Campaign Planning).",
  },
  {
    key: "gcalInvitedGhl", label: "GCal Inv (GHL)", group: "Base", format: "number",
    description: "Contacts whose GHL Calendar webinar series history includes this webinar number.",
    source: "Count of contacts whose GHL contact field 'Calendar webinar series history' contains the token e{N}. At webinar level comes from a single GHL count API call; at list level joins Planning contacts to GHL contacts by email.",
  },

  // ── Delivery ──
  {
    key: "invited", label: "Invited", group: "Delivery", format: "number",
    description: "Total contacts invited to this webinar (the denominator for response-rate metrics).",
    source: "Sum of WebinarListAssignment.volume (same as List Size at list level).",
  },
  {
    key: "unsubscribes", label: "Unsubs", group: "Delivery", format: "number",
    description: "Contacts who unsubscribed during the window between the previous webinar and this one.",
    source: "GHL contacts with 'Cold Calendar unsubscribe date' between the previous webinar date and this webinar date (30-day fallback window when no prior webinar exists).",
  },
  {
    key: "unsubPercent", label: "Unsub %", group: "Delivery", format: "percent",
    formulaText: "unsubscribes / invited",
    description: "Unsubscribe rate relative to invited contacts.",
  },
  {
    key: "ghlPageViews", label: "Page Views", group: "Delivery", format: "number",
    description: "GHL landing page views for this webinar.",
    source: "Not currently synced — intentionally skipped per product decision.",
  },
  {
    key: "ctrPercent", label: "CTR %", group: "Delivery", format: "percent",
    formulaText: "ghlPageViews / invited",
    description: "Click-through rate from invite to landing page.",
  },
  {
    key: "lpRegs", label: "LP Regs", group: "Delivery", format: "number",
    description: "Landing page registrations in this webinar's window.",
    source: "GHL contacts with 'Webinar_Registration_in_form_date' between the previous and current webinar dates (same formula as selfRegMarked).",
  },
  {
    key: "lpRegPercent", label: "LP Reg %", group: "Delivery", format: "percent",
    formulaText: "lpRegs / ghlPageViews",
    description: "Landing page conversion rate (regs per page view).",
  },

  // ── Yes ──
  {
    key: "yesMarked", label: "Marked", group: "Yes", format: "number",
    description: "Contacts who marked Yes on the Google Calendar invite for this webinar.",
    source: "GHL contacts whose 'Calendar invite response history' matches the token e{N}-Yes.",
  },
  {
    key: "yesPer1kInv", label: "/1k Inv", group: "Yes", format: "per1k",
    formulaText: "yesMarked / (invited / 1000)",
    description: "Yes responders per 1,000 invited.",
  },
  {
    key: "yesPercent", label: "% Inv", group: "Yes", format: "percent",
    formulaText: "yesMarked / invited",
    description: "Yes response rate relative to invited.",
  },
  {
    key: "yesAttended", label: "Attended", group: "Yes", format: "number",
    description: "Yes-responders who actually attended the webinar.",
    source: "GHL contacts matching e{N}-Yes, joined to WebinarGeek subscribers (watched_live = true OR minutes_viewing > 0) for the webinar's broadcast_id.",
  },
  {
    key: "yesAttendPercent", label: "Attend %", group: "Yes", format: "percent",
    formulaText: "yesAttended / yesMarked",
    description: "Of the Yes-responders, what % actually attended.",
  },
  {
    key: "yes10MinPlus", label: "10m+", group: "Yes", format: "number",
    description: "Yes-responders who watched 10 minutes or more of the live broadcast.",
    source: "Same as Yes Attended but with WebinarGeek minutes_viewing >= 10.",
  },
  {
    key: "yesStay10MinPercent", label: "Stay 10m %", group: "Yes", format: "percent",
    formulaText: "yes10MinPlus / yesAttended",
    description: "Of Yes attendees, what % watched at least 10 minutes.",
  },
  {
    key: "yesAttendBySmsClick", label: "SMS Click", group: "Yes", format: "number",
    description: "Yes-attendees who also carry the 'webinar reminder sms clicked' tag.",
    source: "Yes-attendees intersected with GHL contacts where has_sms_click_tag = true.",
  },
  {
    key: "yesAttendBySmsClickPercent", label: "SMS %", group: "Yes", format: "percent",
    formulaText: "yesAttendBySmsClick / yesAttended",
    description: "Share of Yes attendees driven by the SMS reminder click.",
  },
  {
    key: "yesBookings", label: "Bookings", group: "Yes", format: "number",
    description: "Yes-responders who subsequently booked a call tied to this webinar.",
    source: "GHL contacts matching e{N}-Yes AND Booked_call_webinar_series = {N}.",
  },
  {
    key: "yesBookingsPer1kInv", label: "Book/1k", group: "Yes", format: "per1k",
    formulaText: "yesBookings / (invited / 1000)",
    description: "Yes-bookings per 1,000 invited.",
  },

  // ── Maybe ──
  {
    key: "maybeMarked", label: "Marked", group: "Maybe", format: "number",
    description: "Contacts who marked Maybe on the GCal invite.",
    source: "GHL contacts whose 'Calendar invite response history' matches e{N}-Maybe.",
  },
  {
    key: "maybePer1kInv", label: "/1k Inv", group: "Maybe", format: "per1k",
    formulaText: "maybeMarked / (invited / 1000)",
    description: "Maybe responders per 1,000 invited.",
  },
  {
    key: "maybeAttended", label: "Attended", group: "Maybe", format: "number",
    description: "Maybe-responders who attended the webinar.",
    source: "Same as Yes Attended but filtered on e{N}-Maybe.",
  },
  {
    key: "maybeAttendPercent", label: "Attend %", group: "Maybe", format: "percent",
    formulaText: "maybeAttended / maybeMarked",
    description: "Of Maybe-responders, what % attended.",
  },
  {
    key: "maybe10MinPlus", label: "10m+", group: "Maybe", format: "number",
    description: "Maybe attendees who watched ≥10 minutes.",
    source: "Same as Maybe Attended with minutes_viewing >= 10.",
  },
  {
    key: "maybeStay10MinPercent", label: "Stay 10m %", group: "Maybe", format: "percent",
    formulaText: "maybe10MinPlus / maybeAttended",
    description: "Of Maybe attendees, what % stayed 10 minutes+.",
  },
  {
    key: "maybeAttendBySmsClick", label: "SMS Click", group: "Maybe", format: "number",
    description: "Maybe attendees with the 'webinar reminder sms clicked' tag.",
    source: "Maybe-attendees intersected with has_sms_click_tag = true.",
  },
  {
    key: "maybeAttendBySmsClickPercent", label: "SMS %", group: "Maybe", format: "percent",
    formulaText: "maybeAttendBySmsClick / maybeAttended",
    description: "Share of Maybe attendees driven by the SMS reminder click.",
  },
  {
    key: "maybeBookings", label: "Bookings", group: "Maybe", format: "number",
    description: "Maybe-responders who booked a call for this webinar.",
    source: "GHL contacts matching e{N}-Maybe AND Booked_call_webinar_series = {N}.",
  },
  {
    key: "maybeBookingsPer1kInv", label: "Book/1k", group: "Maybe", format: "per1k",
    formulaText: "maybeBookings / (invited / 1000)",
    description: "Maybe-bookings per 1,000 invited.",
  },

  // ── Self Reg ──
  {
    key: "selfRegMarked", label: "Marked", group: "Self Reg", format: "number",
    description: "Contacts who self-registered via the landing page in this webinar's window.",
    source: "GHL contacts with 'Webinar_Registration_in_form_date' between the previous webinar date and this one.",
  },
  {
    key: "selfRegPer1kInv", label: "/1k Inv", group: "Self Reg", format: "per1k",
    formulaText: "selfRegMarked / (invited / 1000)",
    description: "Self-registrations per 1,000 invited.",
  },
  {
    key: "selfRegAttended", label: "Attended", group: "Self Reg", format: "number",
    description: "Self-registrants who actually attended.",
    source: "Self-registrants (date window) joined to WebinarGeek subscribers for this broadcast with watched_live OR minutes_viewing > 0.",
  },
  {
    key: "selfRegAttendPercent", label: "Attend %", group: "Self Reg", format: "percent",
    formulaText: "selfRegAttended / selfRegMarked",
    description: "Of self-registrants, what % attended.",
  },
  {
    key: "selfReg10MinPlus", label: "10m+", group: "Self Reg", format: "number",
    description: "Self-registrants who watched ≥10 minutes.",
    source: "Same as Self-Reg Attended with minutes_viewing >= 10.",
  },
  {
    key: "selfRegStay10MinPercent", label: "Stay 10m %", group: "Self Reg", format: "percent",
    formulaText: "selfReg10MinPlus / selfRegAttended",
    description: "Of self-reg attendees, what % stayed 10 minutes+.",
  },
  {
    key: "selfRegBookings", label: "Bookings", group: "Self Reg", format: "number",
    description: "Self-registrants who booked a call for this webinar.",
    source: "Self-reg date window + Booked_call_webinar_series = {N}.",
  },
  {
    key: "selfRegBookingsPer1kInv", label: "Book/1k", group: "Self Reg", format: "per1k",
    formulaText: "selfRegBookings / (invited / 1000)",
    description: "Self-reg bookings per 1,000 invited.",
  },

  // ── Attendance ──
  {
    key: "totalRegs", label: "Total Regs", group: "Attendance", format: "number",
    description: "All WebinarGeek registrations for this broadcast (ignoring response channel).",
    source: "Count of webinargeek_subscribers rows with broadcast_id = this webinar's linked WG broadcast.",
  },
  {
    key: "invitedToRegPercent", label: "Inv>Reg %", group: "Attendance", format: "percent",
    formulaText: "totalRegs / invited",
    description: "Percentage of invited contacts who registered via WG.",
  },
  {
    key: "totalAttended", label: "Attended", group: "Attendance", format: "number",
    description: "All WebinarGeek attendees (regardless of channel).",
    source: "webinargeek_subscribers with broadcast_id = this webinar AND (watched_live = true OR minutes_viewing > 0).",
  },
  {
    key: "regToAttendPercent", label: "Reg>Att %", group: "Attendance", format: "percent",
    formulaText: "totalAttended / totalRegs",
    description: "Of WG registrants, what % attended.",
  },
  {
    key: "invitedToAttendPercent", label: "Inv>Att %", group: "Attendance", format: "percent",
    formulaText: "totalAttended / invited",
    description: "Invited-to-attended conversion rate.",
  },
  {
    key: "totalAttendedPer1kInv", label: "Att/1k", group: "Attendance", format: "per1k",
    formulaText: "totalAttended / (invited / 1000)",
    description: "Attendees per 1,000 invited.",
  },
  {
    key: "attendBySmsReminder", label: "SMS Remind", group: "Attendance", format: "number",
    description: "Total attendees who carry the 'webinar reminder sms clicked' tag.",
    source: "WG attendees ∩ GHL contacts with has_sms_click_tag = true.",
  },
  {
    key: "attendBySmsReminderPercent", label: "SMS Rem %", group: "Attendance", format: "percent",
    formulaText: "attendBySmsReminder / totalAttended",
    description: "Share of attendees attributable to the SMS reminder click.",
  },
  {
    key: "total10MinPlus", label: "10m+", group: "Attendance", format: "number",
    description: "Attendees who watched ≥10 minutes of the live broadcast.",
    source: "WG subscribers with broadcast_id = this webinar AND minutes_viewing >= 10.",
  },
  {
    key: "total10MinPlusPer1kInv", label: "10m/1k", group: "Attendance", format: "per1k",
    formulaText: "total10MinPlus / (invited / 1000)",
    description: "10-minute watchers per 1,000 invited.",
  },
  {
    key: "attend10MinPercent", label: "10m %", group: "Attendance", format: "percent",
    formulaText: "total10MinPlus / totalAttended",
    description: "Of attendees, what % stayed 10 minutes+.",
  },
  {
    key: "total30MinPlus", label: "30m+", group: "Attendance", format: "number",
    description: "Attendees who watched ≥30 minutes.",
    source: "WG subscribers with broadcast_id = this webinar AND minutes_viewing >= 30.",
  },
  {
    key: "total30MinPlusPer1kInv", label: "30m/1k", group: "Attendance", format: "per1k",
    formulaText: "total30MinPlus / (invited / 1000)",
    description: "30-minute watchers per 1,000 invited.",
  },
  {
    key: "attend30MinPercent", label: "30m %", group: "Attendance", format: "percent",
    formulaText: "total30MinPlus / totalAttended",
    description: "Of attendees, what % stayed 30 minutes+.",
  },

  // ── Sales ──
  {
    key: "totalBookings", label: "Bookings", group: "Sales", format: "number",
    description: "All calls booked that are attributed to this webinar.",
    source: "UNION of (GHL opportunities with webinar_source_number = {N}) + (opps whose contact has booked_call_webinar_series = {N}), counted distinct.",
  },
  {
    key: "bookingsPerAttended", label: "Book/Att", group: "Sales", format: "ratio",
    formulaText: "totalBookings / totalAttended",
    description: "Bookings per attendee.",
  },
  {
    key: "bookingsPerPast10Min", label: "Book/10m", group: "Sales", format: "ratio",
    formulaText: "totalBookings / total10MinPlus",
    description: "Bookings per 10-minute viewer.",
  },
  {
    key: "totalBookingsPer1kInv", label: "Book/1k", group: "Sales", format: "per1k",
    formulaText: "totalBookings / (invited / 1000)",
    description: "Bookings per 1,000 invited.",
  },
  {
    key: "totalCallsDatePassed", label: "Calls", group: "Sales", format: "number",
    description: "Opportunities whose Call 1 appointment date has passed.",
    source: "ghl_opportunity rows for this webinar where call1_appointment_date IS NOT NULL AND <= NOW().",
  },
  {
    key: "confirmed", label: "Confirmed", group: "Sales", format: "number",
    description: "Opportunities with Call 1 status = Confirmed.",
    source: "ghl_opportunity.call1_appointment_status = 'Confirmed' (case-insensitive).",
  },
  {
    key: "shows", label: "Shows", group: "Sales", format: "number",
    description: "Opportunities whose first call showed up.",
    source: "ghl_opportunity.call1_appointment_status = 'Showed'.",
  },
  {
    key: "showPercent", label: "Show %", group: "Sales", format: "percent",
    formulaText: "shows / totalBookings",
    description: "Show-up rate for booked calls.",
  },
  {
    key: "noShows", label: "No Shows", group: "Sales", format: "number",
    description: "Opportunities that no-showed on Call 1.",
    source: "ghl_opportunity.call1_appointment_status IN ('noshow','no show','no-show').",
  },
  {
    key: "canceled", label: "Canceled", group: "Sales", format: "number",
    description: "Opportunities whose Call 1 was cancelled.",
    source: "ghl_opportunity.call1_appointment_status = 'Cancelled'.",
  },
  {
    key: "won", label: "Won", group: "Sales", format: "number",
    description: "Opportunities that reached the Deal Won pipeline stage.",
    source: "ghl_opportunity.pipeline_stage_id = Deal Won stage (544b178f-...).",
  },
  {
    key: "closeRatePercent", label: "Close %", group: "Sales", format: "percent",
    formulaText: "won / shows",
    description: "Close rate on calls that actually showed up.",
  },
  {
    key: "avgProjectedDealSize", label: "Proj Deal $", group: "Sales", format: "currency",
    description: "Average projected deal size across opportunities (each option mapped to its numeric value).",
    source: "Mean of ghl_opportunity.projected_deal_size_value for this webinar's opps (Projected Deal Size dropdown: 7,700 / 15,000 / 20,000 / 25,000).",
  },
  {
    key: "avgClosedDealValue", label: "Closed $", group: "Sales", format: "currency",
    description: "Total closed-won monetary value.",
    source: "Sum of ghl_opportunity.monetary_value for opps in the Deal Won stage.",
  },

  // ── Quality ──
  {
    key: "disqualified", label: "DQ", group: "Quality", format: "number",
    description: "Opportunities in the Disqualified pipeline stage.",
    source: "ghl_opportunity.pipeline_stage_id = Disqualified stage (62448525-...).",
  },
  {
    key: "qualified", label: "Qualified", group: "Quality", format: "number",
    description: "Shows whose Lead Quality is non-DQ (Great / Ok / Barely Passable).",
    source: "ghl_opportunity.call1_appointment_status = 'Showed' AND lead_quality IN ('Great','Ok','Barely Passable').",
  },
  {
    key: "qualPercent", label: "Qual %", group: "Quality", format: "percent",
    formulaText: "qualified / shows",
    description: "Of shows, what % were qualified.",
  },
  {
    key: "leadQualityGreat", label: "Great", group: "Quality", format: "number",
    description: "Opportunities rated lead quality 'Great'.",
    source: "ghl_opportunity.lead_quality = 'Great'.",
  },
  {
    key: "leadQualityOk", label: "Ok", group: "Quality", format: "number",
    description: "Opportunities rated lead quality 'Ok'.",
    source: "ghl_opportunity.lead_quality = 'Ok'.",
  },
  {
    key: "leadQualityBarelyPassable", label: "Barely", group: "Quality", format: "number",
    description: "Opportunities rated 'Barely Passable'.",
    source: "ghl_opportunity.lead_quality = 'Barely Passable'.",
  },
  {
    key: "leadQualityBadDq", label: "Bad/DQ", group: "Quality", format: "number",
    description: "Opportunities rated 'Bad / DQ'.",
    source: "ghl_opportunity.lead_quality = 'Bad / DQ'.",
  },
];

/** Count columns per group for header colSpan. */
export function columnsInGroup(group: MetricGroup): number {
  return METRIC_COLUMNS.filter((c) => c.group === group).length;
}

/** Get columns for a specific group. */
export function columnsForGroup(group: MetricGroup): MetricColumn[] {
  return METRIC_COLUMNS.filter((c) => c.group === group);
}

/** True if this column is the first in its metric group (used to render
 * a visible vertical separator between metric bands). */
export function isGroupBoundary(colIndex: number): boolean {
  if (colIndex === 0) return true;
  return METRIC_COLUMNS[colIndex].group !== METRIC_COLUMNS[colIndex - 1].group;
}

/** Tailwind classes applied to the first cell of each metric group, so the
 * Base/Delivery/Yes/Maybe/... bands are visually separated. */
export const GROUP_BOUNDARY_CLASSES = "border-l-2 border-zinc-300 dark:border-zinc-700/60";

/**
 * Format a metric value for table display.
 * null/undefined -> "—" (em dash), numbers formatted per column spec.
 */
export function formatMetricValue(
  value: number | null | undefined,
  col: MetricColumn,
): string {
  if (value === null || value === undefined) return "—";
  const d = col.decimals ?? (col.format === "number" ? 0 : col.format === "currency" ? 0 : 2);
  switch (col.format) {
    case "number":
      return d === 0 ? Math.round(value).toLocaleString() : value.toFixed(d);
    case "percent":
      return (value * 100).toFixed(d) + "%";
    case "per1k":
      return value.toFixed(d);
    case "currency":
      return "$" + Math.round(value).toLocaleString();
    case "ratio":
      return value.toFixed(d);
  }
}
