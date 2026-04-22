export type MetricFormat = "number" | "percent" | "per1k" | "currency" | "ratio";
export type MetricGroup = "Base" | "Delivery" | "Yes" | "Maybe" | "Self Reg" | "Attendance" | "Sales" | "Quality";

export interface MetricColumn {
  key: string;
  label: string;
  group: MetricGroup;
  format: MetricFormat;
  decimals?: number;
  formulaText?: string;
}

export const METRIC_GROUPS: MetricGroup[] = [
  "Base", "Delivery", "Yes", "Maybe", "Self Reg", "Attendance", "Sales", "Quality",
];

export const METRIC_COLUMNS: MetricColumn[] = [
  // ── Base ──
  { key: "listSize", label: "List Size", group: "Base", format: "number" },
  { key: "listRemain", label: "Remain", group: "Base", format: "number" },
  { key: "accountsNeeded", label: "Accts", group: "Base", format: "number", decimals: 1 },
  { key: "gcalInvited", label: "GCal Inv", group: "Base", format: "number" },
  { key: "gcalInvitedGhl", label: "GCal Inv (GHL)", group: "Base", format: "number", formulaText: "count of GHL contacts with e{N} in Calendar webinar series history" },

  // ── Delivery ──
  { key: "invited", label: "Invited", group: "Delivery", format: "number" },
  { key: "unsubscribes", label: "Unsubs", group: "Delivery", format: "number" },
  { key: "unsubPercent", label: "Unsub %", group: "Delivery", format: "percent", formulaText: "unsubscribes / invited" },
  { key: "ghlPageViews", label: "Page Views", group: "Delivery", format: "number" },
  { key: "ctrPercent", label: "CTR %", group: "Delivery", format: "percent", formulaText: "ghlPageViews / invited" },
  { key: "lpRegs", label: "LP Regs", group: "Delivery", format: "number" },
  { key: "lpRegPercent", label: "LP Reg %", group: "Delivery", format: "percent", formulaText: "lpRegs / ghlPageViews" },

  // ── Yes ──
  { key: "yesMarked", label: "Marked", group: "Yes", format: "number" },
  { key: "yesPer1kInv", label: "/1k Inv", group: "Yes", format: "per1k", formulaText: "yesMarked / (invited / 1000)" },
  { key: "yesPercent", label: "% Inv", group: "Yes", format: "percent", formulaText: "yesMarked / invited" },
  { key: "yesAttended", label: "Attended", group: "Yes", format: "number" },
  { key: "yesAttendPercent", label: "Attend %", group: "Yes", format: "percent", formulaText: "yesAttended / yesMarked" },
  { key: "yes10MinPlus", label: "10m+", group: "Yes", format: "number" },
  { key: "yesStay10MinPercent", label: "Stay 10m %", group: "Yes", format: "percent", formulaText: "yes10MinPlus / yesAttended" },
  { key: "yesAttendBySmsClick", label: "SMS Click", group: "Yes", format: "number" },
  { key: "yesAttendBySmsClickPercent", label: "SMS %", group: "Yes", format: "percent", formulaText: "yesAttendBySmsClick / yesAttended" },
  { key: "yesBookings", label: "Bookings", group: "Yes", format: "number" },
  { key: "yesBookingsPer1kInv", label: "Book/1k", group: "Yes", format: "per1k", formulaText: "yesBookings / (invited / 1000)" },

  // ── Maybe ──
  { key: "maybeMarked", label: "Marked", group: "Maybe", format: "number" },
  { key: "maybePer1kInv", label: "/1k Inv", group: "Maybe", format: "per1k", formulaText: "maybeMarked / (invited / 1000)" },
  { key: "maybeAttended", label: "Attended", group: "Maybe", format: "number" },
  { key: "maybeAttendPercent", label: "Attend %", group: "Maybe", format: "percent", formulaText: "maybeAttended / maybeMarked" },
  { key: "maybe10MinPlus", label: "10m+", group: "Maybe", format: "number" },
  { key: "maybeStay10MinPercent", label: "Stay 10m %", group: "Maybe", format: "percent", formulaText: "maybe10MinPlus / maybeAttended" },
  { key: "maybeAttendBySmsClick", label: "SMS Click", group: "Maybe", format: "number" },
  { key: "maybeAttendBySmsClickPercent", label: "SMS %", group: "Maybe", format: "percent", formulaText: "maybeAttendBySmsClick / maybeAttended" },
  { key: "maybeBookings", label: "Bookings", group: "Maybe", format: "number" },
  { key: "maybeBookingsPer1kInv", label: "Book/1k", group: "Maybe", format: "per1k", formulaText: "maybeBookings / (invited / 1000)" },

  // ── Self Reg ──
  { key: "selfRegMarked", label: "Marked", group: "Self Reg", format: "number" },
  { key: "selfRegPer1kInv", label: "/1k Inv", group: "Self Reg", format: "per1k", formulaText: "selfRegMarked / (invited / 1000)" },
  { key: "selfRegAttended", label: "Attended", group: "Self Reg", format: "number" },
  { key: "selfRegAttendPercent", label: "Attend %", group: "Self Reg", format: "percent", formulaText: "selfRegAttended / selfRegMarked" },
  { key: "selfReg10MinPlus", label: "10m+", group: "Self Reg", format: "number" },
  { key: "selfRegStay10MinPercent", label: "Stay 10m %", group: "Self Reg", format: "percent", formulaText: "selfReg10MinPlus / selfRegAttended" },
  { key: "selfRegBookings", label: "Bookings", group: "Self Reg", format: "number" },
  { key: "selfRegBookingsPer1kInv", label: "Book/1k", group: "Self Reg", format: "per1k", formulaText: "selfRegBookings / (invited / 1000)" },

  // ── Attendance ──
  { key: "totalRegs", label: "Total Regs", group: "Attendance", format: "number" },
  { key: "invitedToRegPercent", label: "Inv>Reg %", group: "Attendance", format: "percent", formulaText: "totalRegs / invited" },
  { key: "totalAttended", label: "Attended", group: "Attendance", format: "number" },
  { key: "regToAttendPercent", label: "Reg>Att %", group: "Attendance", format: "percent", formulaText: "totalAttended / totalRegs" },
  { key: "invitedToAttendPercent", label: "Inv>Att %", group: "Attendance", format: "percent", formulaText: "totalAttended / invited" },
  { key: "totalAttendedPer1kInv", label: "Att/1k", group: "Attendance", format: "per1k", formulaText: "totalAttended / (invited / 1000)" },
  { key: "attendBySmsReminder", label: "SMS Remind", group: "Attendance", format: "number" },
  { key: "attendBySmsReminderPercent", label: "SMS Rem %", group: "Attendance", format: "percent", formulaText: "attendBySmsReminder / totalAttended" },
  { key: "total10MinPlus", label: "10m+", group: "Attendance", format: "number" },
  { key: "total10MinPlusPer1kInv", label: "10m/1k", group: "Attendance", format: "per1k", formulaText: "total10MinPlus / (invited / 1000)" },
  { key: "attend10MinPercent", label: "10m %", group: "Attendance", format: "percent", formulaText: "total10MinPlus / totalAttended" },
  { key: "total30MinPlus", label: "30m+", group: "Attendance", format: "number" },
  { key: "total30MinPlusPer1kInv", label: "30m/1k", group: "Attendance", format: "per1k", formulaText: "total30MinPlus / (invited / 1000)" },
  { key: "attend30MinPercent", label: "30m %", group: "Attendance", format: "percent", formulaText: "total30MinPlus / totalAttended" },

  // ── Sales ──
  { key: "totalBookings", label: "Bookings", group: "Sales", format: "number" },
  { key: "bookingsPerAttended", label: "Book/Att", group: "Sales", format: "ratio", formulaText: "totalBookings / totalAttended" },
  { key: "bookingsPerPast10Min", label: "Book/10m", group: "Sales", format: "ratio", formulaText: "totalBookings / total10MinPlus" },
  { key: "totalBookingsPer1kInv", label: "Book/1k", group: "Sales", format: "per1k", formulaText: "totalBookings / (invited / 1000)" },
  { key: "totalCallsDatePassed", label: "Calls", group: "Sales", format: "number" },
  { key: "confirmed", label: "Confirmed", group: "Sales", format: "number" },
  { key: "shows", label: "Shows", group: "Sales", format: "number" },
  { key: "showPercent", label: "Show %", group: "Sales", format: "percent", formulaText: "shows / totalBookings" },
  { key: "noShows", label: "No Shows", group: "Sales", format: "number" },
  { key: "canceled", label: "Canceled", group: "Sales", format: "number" },
  { key: "won", label: "Won", group: "Sales", format: "number" },
  { key: "closeRatePercent", label: "Close %", group: "Sales", format: "percent", formulaText: "won / shows" },
  { key: "avgProjectedDealSize", label: "Proj Deal $", group: "Sales", format: "currency" },
  { key: "avgClosedDealValue", label: "Closed $", group: "Sales", format: "currency" },

  // ── Quality ──
  { key: "disqualified", label: "DQ", group: "Quality", format: "number" },
  { key: "qualified", label: "Qualified", group: "Quality", format: "number" },
  { key: "qualPercent", label: "Qual %", group: "Quality", format: "percent", formulaText: "qualified / shows" },
  { key: "leadQualityGreat", label: "Great", group: "Quality", format: "number" },
  { key: "leadQualityOk", label: "Ok", group: "Quality", format: "number" },
  { key: "leadQualityBarelyPassable", label: "Barely", group: "Quality", format: "number" },
  { key: "leadQualityBadDq", label: "Bad/DQ", group: "Quality", format: "number" },
];

/** Count columns per group for header colSpan. */
export function columnsInGroup(group: MetricGroup): number {
  return METRIC_COLUMNS.filter((c) => c.group === group).length;
}

/** Get columns for a specific group. */
export function columnsForGroup(group: MetricGroup): MetricColumn[] {
  return METRIC_COLUMNS.filter((c) => c.group === group);
}

/**
 * Format a metric value for table display.
 * null/undefined -> "\u2014" (em dash), numbers formatted per column spec.
 */
export function formatMetricValue(
  value: number | null | undefined,
  col: MetricColumn,
): string {
  if (value === null || value === undefined) return "\u2014";
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
