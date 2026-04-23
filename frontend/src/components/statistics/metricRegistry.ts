export type MetricFormat = "number" | "percent" | "per1k" | "currency" | "ratio";
export type MetricGroup = "Base" | "Delivery" | "Yes" | "Maybe" | "Self Reg" | "Attendance" | "Sales" | "Quality";

export type FieldEntity =
  | "GHL Contact"
  | "GHL Opportunity"
  | "WebinarGeek Subscriber"
  | "Planning Assignment"
  | "Webinar"
  | "Computed";

/**
 * One underlying data field a metric reads from. Rendered as a row in the
 * info modal so operators can trace each number back to GHL / WebinarGeek
 * / the Planning DB.
 */
export interface FieldRef {
  entity: FieldEntity;
  /** Human-readable field name (e.g. "Calendar invite response history"). */
  field: string;
  /** GHL custom field ID when applicable, e.g. "ghPIByTtKxRmHveNu4b1". */
  fieldId?: string;
  /** Filter applied to this field for this metric, e.g. "contains 'e{N}-Yes'". */
  filter?: string;
}

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
  /** Narrative explanation of data source + filter (shown as prose in the modal). */
  source?: string;
  /** Structured list of fields this metric reads from (shown as a table). */
  fieldsUsed?: FieldRef[];
}

// ── Reusable FieldRef presets for the common GHL / WG / Planning columns ──
// These are defined once and referenced with the spread operator below so
// field IDs stay consistent and centrally updatable.

const F_WLA_VOLUME: FieldRef = { entity: "Planning Assignment", field: "volume" };
const F_WLA_REMAIN: FieldRef = { entity: "Planning Assignment", field: "remaining" };
const F_WLA_GCAL: FieldRef = { entity: "Planning Assignment", field: "gcal_invited" };
const F_WLA_ACCTS: FieldRef = { entity: "Planning Assignment", field: "accounts_used" };

const F_CONTACT_INVITE_RESP: FieldRef = {
  entity: "GHL Contact",
  field: "Calendar invite response history",
  fieldId: "ghPIByTtKxRmHveNu4b1",
};
const F_CONTACT_SERIES_HISTORY: FieldRef = {
  entity: "GHL Contact",
  field: "Calendar webinar series history",
  fieldId: "6YyME5pcbkr2zpxMHDPK",
};
const F_CONTACT_NON_JOINERS: FieldRef = {
  entity: "GHL Contact",
  field: "Calendar webinar series non joiners",
  fieldId: "6TYlHOaOXS2DWHH5kR8D",
};
const F_CONTACT_BOOKED_CALL: FieldRef = {
  entity: "GHL Contact",
  field: "Booked_call_webinar_series",
  fieldId: "rsgthoV5ScH49VPFZlyq",
};
const F_CONTACT_REG_DATE: FieldRef = {
  entity: "GHL Contact",
  field: "Webinar_Registration_in_form_date",
  fieldId: "PUuRqljS3gWyBEmwBxwL",
};
const F_CONTACT_UNSUB_DATE: FieldRef = {
  entity: "GHL Contact",
  field: "Cold Calendar unsubscribe date",
  fieldId: "OLQt9nEWyG7tpYIdNs4F",
};
const F_CONTACT_SMS_TAG: FieldRef = {
  entity: "GHL Contact",
  field: "tags[] (derived to has_sms_click_tag)",
  filter: "contains 'webinar reminder sms clicked'",
};

const F_WG_BROADCAST: FieldRef = {
  entity: "WebinarGeek Subscriber",
  field: "broadcast_id",
  filter: "= webinar.broadcast_id",
};
const F_WG_WATCHED: FieldRef = {
  entity: "WebinarGeek Subscriber",
  field: "watched_live / minutes_viewing",
  filter: "watched_live = true OR minutes_viewing > 0",
};

const F_OPP_WEBINAR_SRC: FieldRef = {
  entity: "GHL Opportunity",
  field: "Webinar Source Number v2",
  fieldId: "gp70TwLRM9Tnsfr7FR9Y",
  filter: "= {N}",
};
const F_OPP_CALL1_STATUS: FieldRef = {
  entity: "GHL Opportunity",
  field: "call1_appointment_status",
  fieldId: "V82ErbW24izA5aQUzRUv",
};
const F_OPP_CALL1_DATE: FieldRef = {
  entity: "GHL Opportunity",
  field: "call1_appointment_date",
  fieldId: "bFDWu3koncdxn26h6nAm",
};
const F_OPP_STAGE: FieldRef = {
  entity: "GHL Opportunity",
  field: "pipeline_stage_id",
};
const F_OPP_LEAD_QUALITY: FieldRef = {
  entity: "GHL Opportunity",
  field: "Lead Quality",
  fieldId: "M8RuTSXsLhZMvdMWAlLr",
};
const F_OPP_PROJECTED: FieldRef = {
  entity: "GHL Opportunity",
  field: "Projected Deal Size",
  fieldId: "Oo9ktilF7QwTNBzksT3k",
};
const F_OPP_MONETARY: FieldRef = {
  entity: "GHL Opportunity",
  field: "monetaryValue",
};

export const METRIC_GROUPS: MetricGroup[] = [
  "Base", "Delivery", "Yes", "Maybe", "Self Reg", "Attendance", "Sales", "Quality",
];

export const METRIC_COLUMNS: MetricColumn[] = [
  // ── Base ──
  {
    key: "listSize", label: "List Size", group: "Base", format: "number",
    description: "Number of contacts planned for this list in Campaign Planning.",
    fieldsUsed: [{ ...F_WLA_VOLUME, filter: "SUM over assignments where webinar_id = this webinar" }],
  },
  {
    key: "listRemain", label: "Remain", group: "Base", format: "number",
    description: "Planned contacts still remaining (not yet used).",
    fieldsUsed: [{ ...F_WLA_REMAIN, filter: "SUM over assignments" }],
  },
  {
    key: "accountsNeeded", label: "Accts", group: "Base", format: "number", decimals: 1,
    description: "Sender accounts needed to deliver this list at the planned volume.",
    fieldsUsed: [{ ...F_WLA_ACCTS, filter: "SUM over assignments" }],
  },
  {
    key: "gcalInvited", label: "GCal Inv", group: "Base", format: "number",
    description: "Google Calendar invite count recorded on the Planning assignment (manually entered).",
    fieldsUsed: [{ ...F_WLA_GCAL, filter: "SUM over assignments" }],
  },
  {
    key: "gcalInvitedGhl", label: "GCal Inv (GHL)", group: "Base", format: "number",
    description: "Contacts whose GHL Calendar webinar series history includes this webinar number. At webinar level a single GHL API count call; at list level joins Planning contacts to GHL contacts by email.",
    fieldsUsed: [{ ...F_CONTACT_SERIES_HISTORY, filter: "contains 'e{N}' (word-boundary \\\\y)" }],
  },

  // ── Delivery ──
  {
    key: "invited", label: "Invited", group: "Delivery", format: "number",
    description: "Total contacts invited to this webinar (the denominator for response-rate metrics).",
    fieldsUsed: [{ ...F_WLA_VOLUME, filter: "SUM over assignments (= List Size)" }],
  },
  {
    key: "unsubscribes", label: "Unsubs", group: "Delivery", format: "number",
    description: "Contacts who unsubscribed during the window between the previous webinar and this one (30-day fallback when no prior webinar).",
    fieldsUsed: [{
      ...F_CONTACT_UNSUB_DATE,
      filter: "BETWEEN prev_webinar_date AND current_webinar_date",
    }],
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
    description: "Landing page registrations in this webinar's window (same formula as Self Reg Marked).",
    fieldsUsed: [{
      ...F_CONTACT_REG_DATE,
      filter: "BETWEEN prev_webinar_date AND current_webinar_date",
    }],
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
    fieldsUsed: [{ ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Yes' (word-boundary)" }],
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
    description: "Yes-responders who attended the webinar — joins GHL contacts to WebinarGeek subscribers by email.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Yes'" },
      F_WG_BROADCAST,
      F_WG_WATCHED,
    ],
  },
  {
    key: "yesAttendPercent", label: "Attend %", group: "Yes", format: "percent",
    formulaText: "yesAttended / yesMarked",
    description: "Of the Yes-responders, what % actually attended.",
  },
  {
    key: "yes10MinPlus", label: "10m+", group: "Yes", format: "number",
    description: "Yes-responders who watched 10 minutes or more of the live broadcast.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Yes'" },
      F_WG_BROADCAST,
      { entity: "WebinarGeek Subscriber", field: "minutes_viewing", filter: ">= 10" },
    ],
  },
  {
    key: "yesStay10MinPercent", label: "Stay 10m %", group: "Yes", format: "percent",
    formulaText: "yes10MinPlus / yesAttended",
    description: "Of Yes attendees, what % watched at least 10 minutes.",
  },
  {
    key: "yesAttendBySmsClick", label: "SMS Click", group: "Yes", format: "number",
    description: "Yes-attendees who also clicked the SMS reminder.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Yes'" },
      F_WG_BROADCAST, F_WG_WATCHED,
      F_CONTACT_SMS_TAG,
    ],
  },
  {
    key: "yesAttendBySmsClickPercent", label: "SMS %", group: "Yes", format: "percent",
    formulaText: "yesAttendBySmsClick / yesAttended",
    description: "Share of Yes attendees driven by the SMS reminder click.",
  },
  {
    key: "yesBookings", label: "Bookings", group: "Yes", format: "number",
    description: "Yes-responders who subsequently booked a call tied to this webinar.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Yes'" },
      { ...F_CONTACT_BOOKED_CALL, filter: "= {N}" },
    ],
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
    fieldsUsed: [{ ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Maybe'" }],
  },
  {
    key: "maybePer1kInv", label: "/1k Inv", group: "Maybe", format: "per1k",
    formulaText: "maybeMarked / (invited / 1000)",
    description: "Maybe responders per 1,000 invited.",
  },
  {
    key: "maybeAttended", label: "Attended", group: "Maybe", format: "number",
    description: "Maybe-responders who attended the webinar.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Maybe'" },
      F_WG_BROADCAST, F_WG_WATCHED,
    ],
  },
  {
    key: "maybeAttendPercent", label: "Attend %", group: "Maybe", format: "percent",
    formulaText: "maybeAttended / maybeMarked",
    description: "Of Maybe-responders, what % attended.",
  },
  {
    key: "maybe10MinPlus", label: "10m+", group: "Maybe", format: "number",
    description: "Maybe attendees who watched ≥10 minutes.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Maybe'" },
      F_WG_BROADCAST,
      { entity: "WebinarGeek Subscriber", field: "minutes_viewing", filter: ">= 10" },
    ],
  },
  {
    key: "maybeStay10MinPercent", label: "Stay 10m %", group: "Maybe", format: "percent",
    formulaText: "maybe10MinPlus / maybeAttended",
    description: "Of Maybe attendees, what % stayed 10 minutes+.",
  },
  {
    key: "maybeAttendBySmsClick", label: "SMS Click", group: "Maybe", format: "number",
    description: "Maybe attendees who also clicked the SMS reminder.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Maybe'" },
      F_WG_BROADCAST, F_WG_WATCHED,
      F_CONTACT_SMS_TAG,
    ],
  },
  {
    key: "maybeAttendBySmsClickPercent", label: "SMS %", group: "Maybe", format: "percent",
    formulaText: "maybeAttendBySmsClick / maybeAttended",
    description: "Share of Maybe attendees driven by the SMS reminder click.",
  },
  {
    key: "maybeBookings", label: "Bookings", group: "Maybe", format: "number",
    description: "Maybe-responders who booked a call for this webinar.",
    fieldsUsed: [
      { ...F_CONTACT_INVITE_RESP, filter: "contains 'e{N}-Maybe'" },
      { ...F_CONTACT_BOOKED_CALL, filter: "= {N}" },
    ],
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
    fieldsUsed: [{ ...F_CONTACT_REG_DATE, filter: "BETWEEN prev_webinar_date AND current_webinar_date" }],
  },
  {
    key: "selfRegPer1kInv", label: "/1k Inv", group: "Self Reg", format: "per1k",
    formulaText: "selfRegMarked / (invited / 1000)",
    description: "Self-registrations per 1,000 invited.",
  },
  {
    key: "selfRegAttended", label: "Attended", group: "Self Reg", format: "number",
    description: "Self-registrants who actually attended.",
    fieldsUsed: [
      { ...F_CONTACT_REG_DATE, filter: "BETWEEN prev_date AND current_date" },
      F_WG_BROADCAST, F_WG_WATCHED,
    ],
  },
  {
    key: "selfRegAttendPercent", label: "Attend %", group: "Self Reg", format: "percent",
    formulaText: "selfRegAttended / selfRegMarked",
    description: "Of self-registrants, what % attended.",
  },
  {
    key: "selfReg10MinPlus", label: "10m+", group: "Self Reg", format: "number",
    description: "Self-registrants who watched ≥10 minutes.",
    fieldsUsed: [
      { ...F_CONTACT_REG_DATE, filter: "BETWEEN prev_date AND current_date" },
      F_WG_BROADCAST,
      { entity: "WebinarGeek Subscriber", field: "minutes_viewing", filter: ">= 10" },
    ],
  },
  {
    key: "selfRegStay10MinPercent", label: "Stay 10m %", group: "Self Reg", format: "percent",
    formulaText: "selfReg10MinPlus / selfRegAttended",
    description: "Of self-reg attendees, what % stayed 10 minutes+.",
  },
  {
    key: "selfRegBookings", label: "Bookings", group: "Self Reg", format: "number",
    description: "Self-registrants who booked a call for this webinar.",
    fieldsUsed: [
      { ...F_CONTACT_REG_DATE, filter: "BETWEEN prev_date AND current_date" },
      { ...F_CONTACT_BOOKED_CALL, filter: "= {N}" },
    ],
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
    fieldsUsed: [F_WG_BROADCAST],
  },
  {
    key: "invitedToRegPercent", label: "Inv>Reg %", group: "Attendance", format: "percent",
    formulaText: "totalRegs / invited",
    description: "Percentage of invited contacts who registered via WG.",
  },
  {
    key: "totalAttended", label: "Attended", group: "Attendance", format: "number",
    description: "All WebinarGeek attendees (regardless of channel).",
    fieldsUsed: [F_WG_BROADCAST, F_WG_WATCHED],
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
    description: "Total attendees who clicked the SMS reminder.",
    fieldsUsed: [F_WG_BROADCAST, F_WG_WATCHED, F_CONTACT_SMS_TAG],
  },
  {
    key: "attendBySmsReminderPercent", label: "SMS Rem %", group: "Attendance", format: "percent",
    formulaText: "attendBySmsReminder / totalAttended",
    description: "Share of attendees attributable to the SMS reminder click.",
  },
  {
    key: "total10MinPlus", label: "10m+", group: "Attendance", format: "number",
    description: "Attendees who watched ≥10 minutes of the live broadcast.",
    fieldsUsed: [F_WG_BROADCAST, { entity: "WebinarGeek Subscriber", field: "minutes_viewing", filter: ">= 10" }],
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
    fieldsUsed: [F_WG_BROADCAST, { entity: "WebinarGeek Subscriber", field: "minutes_viewing", filter: ">= 30" }],
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
    description: "All calls booked for this webinar — UNION of opp-level and contact-level signals (distinct opportunities).",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_CONTACT_BOOKED_CALL, filter: "= {N} (fallback when opp field empty)" }],
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
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_CALL1_DATE, filter: "IS NOT NULL AND <= now()" }],
  },
  {
    key: "confirmed", label: "Confirmed", group: "Sales", format: "number",
    description: "Opportunities with Call 1 status = Confirmed.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_CALL1_STATUS, filter: "= 'Confirmed' (case-insensitive)" }],
  },
  {
    key: "shows", label: "Shows", group: "Sales", format: "number",
    description: "Opportunities whose first call showed up.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_CALL1_STATUS, filter: "= 'Showed'" }],
  },
  {
    key: "showPercent", label: "Show %", group: "Sales", format: "percent",
    formulaText: "shows / totalBookings",
    description: "Show-up rate for booked calls.",
  },
  {
    key: "noShows", label: "No Shows", group: "Sales", format: "number",
    description: "Opportunities that no-showed on Call 1.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_CALL1_STATUS, filter: "IN ('noshow','no show','no-show')" }],
  },
  {
    key: "canceled", label: "Canceled", group: "Sales", format: "number",
    description: "Opportunities whose Call 1 was cancelled.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_CALL1_STATUS, filter: "= 'Cancelled'" }],
  },
  {
    key: "won", label: "Won", group: "Sales", format: "number",
    description: "Opportunities that reached the Deal Won pipeline stage.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_STAGE, filter: "= Deal Won stage (544b178f-d1f2-4186-a8c2-00c3b0eeefe8)" }],
  },
  {
    key: "closeRatePercent", label: "Close %", group: "Sales", format: "percent",
    formulaText: "won / shows",
    description: "Close rate on calls that actually showed up.",
  },
  {
    key: "avgProjectedDealSize", label: "Proj Deal $", group: "Sales", format: "currency",
    description: "Average projected deal size across opportunities (each option mapped to its numeric value: 7,700 / 15,000 / 20,000 / 25,000).",
    fieldsUsed: [F_OPP_WEBINAR_SRC, F_OPP_PROJECTED],
  },
  {
    key: "avgClosedDealValue", label: "Closed $", group: "Sales", format: "currency",
    description: "Total closed-won monetary value (sum, not average, per the v1 spec).",
    fieldsUsed: [F_OPP_WEBINAR_SRC, F_OPP_MONETARY, { ...F_OPP_STAGE, filter: "= Deal Won stage" }],
  },

  // ── Quality ──
  {
    key: "disqualified", label: "DQ", group: "Quality", format: "number",
    description: "Opportunities in the Disqualified pipeline stage.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_STAGE, filter: "= Disqualified stage (62448525-88ab-4e82-b414-b6880e69e2de)" }],
  },
  {
    key: "qualified", label: "Qualified", group: "Quality", format: "number",
    description: "Shows whose Lead Quality is non-DQ (Great / Ok / Barely Passable).",
    fieldsUsed: [
      F_OPP_WEBINAR_SRC,
      { ...F_OPP_CALL1_STATUS, filter: "= 'Showed'" },
      { ...F_OPP_LEAD_QUALITY, filter: "IN ('Great','Ok','Barely Passable')" },
    ],
  },
  {
    key: "qualPercent", label: "Qual %", group: "Quality", format: "percent",
    formulaText: "qualified / shows",
    description: "Of shows, what % were qualified.",
  },
  {
    key: "leadQualityGreat", label: "Great", group: "Quality", format: "number",
    description: "Opportunities rated lead quality 'Great'.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_LEAD_QUALITY, filter: "= 'Great'" }],
  },
  {
    key: "leadQualityOk", label: "Ok", group: "Quality", format: "number",
    description: "Opportunities rated lead quality 'Ok'.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_LEAD_QUALITY, filter: "= 'Ok'" }],
  },
  {
    key: "leadQualityBarelyPassable", label: "Barely", group: "Quality", format: "number",
    description: "Opportunities rated 'Barely Passable'.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_LEAD_QUALITY, filter: "= 'Barely Passable'" }],
  },
  {
    key: "leadQualityBadDq", label: "Bad/DQ", group: "Quality", format: "number",
    description: "Opportunities rated 'Bad / DQ'.",
    fieldsUsed: [F_OPP_WEBINAR_SRC, { ...F_OPP_LEAD_QUALITY, filter: "= 'Bad / DQ'" }],
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
