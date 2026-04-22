# Statistics Formulas — Handoff Reference

This document explains how every metric in the Statistics page is sourced, derived, and aggregated. It serves as the handoff reference for the next engineer or AI model.

## Workbook Shape

- **Sheet**: Webinar Funnel (single sheet)
- **Columns**: A through CK (89 columns). BD–CK are scratch/unused.
- **Rows**: Flat data, no merged cells
- **Parent rows**: Detected by numeric value in column A (webinar number 106–136)
- **Child rows**: Belong to the parent above them until the next parent row

### Parent Row Variants

| Variant | Webinars | Column F value |
|---------|----------|----------------|
| Legacy | 106–121 | `TOTAL` |
| Titled | 122–133 | Title text (e.g. `TITLE: Scale Your Business`) |
| Bare | 134–136 | Blank or minimal |

### Included Row Ranges

- Safe window: rows 2–305
- Webinar 136 (starts row 301): include child rows 302–305 only
- **Excluded**: rows 306–366 (scratch notes, capacity planning, orphan ideas)

## Column Mapping (Excel Letter → API Key)

| Col | API Key | Col | API Key |
|-----|---------|-----|---------|
| A | webinarNumber | B | dateOrNote |
| C | status | D | listUrl |
| E | description | F | listNameOrTitle |
| G | sendInfo | H | descLabel |
| I | titleText | J | listSize |
| K | listRemain | L | gcalInvited |
| M | accountsNeeded | N | createdDate |
| O | industry | P | employeeRange |
| Q | country | R | invited |
| S | unsubscribes | T | ghlPageViews |
| U | lpRegs | V | yesMarked |
| W | yesAttended | X | yes10MinPlus |
| Y | yesAttendBySmsClick | Z | yesBookings |
| AA | maybeMarked | AB | maybeAttended |
| AC | maybe10MinPlus | AD | maybeAttendBySmsClick |
| AE | maybeBookings | AF | selfRegMarked |
| AG | selfRegAttended | AH | selfReg10MinPlus |
| AI | selfRegBookings | AJ | totalRegs |
| AK | totalAttended | AL | attendBySmsReminder |
| AM | total10MinPlus | AN | total30MinPlus |
| AO | totalBookings | AP | totalCallsDatePassed |
| AQ | confirmed | AR | shows |
| AS | noShows | AT | canceled |
| AU | won | AV | disqualified |
| AW | qualified | AX | leadQualityGreat |
| AY | leadQualityOk | AZ | leadQualityBarelyPassable |
| BA | leadQualityBadDq | BB | avgProjectedDealSize |
| BC | avgClosedDealValue | | |

## Source-Fed Fields

These fields come directly from the workbook (v1) or will come from GoHighLevel (v2). They are **not** computed in application code.

`status`, `listUrl`, `description`, `sendInfo`, `descLabel`, `titleText`, `listSize`, `listRemain`, `gcalInvited`, `accountsNeeded`, `createdDate`, `industry`, `employeeRange`, `country`, `invited`, `unsubscribes`, `ghlPageViews`, `lpRegs`, `yesMarked`, `yesAttended`, `yes10MinPlus`, `yesAttendBySmsClick`, `yesBookings`, `maybeMarked`, `maybeAttended`, `maybe10MinPlus`, `maybeAttendBySmsClick`, `maybeBookings`, `selfRegMarked`, `selfRegAttended`, `selfReg10MinPlus`, `selfRegBookings`, `totalRegs`, `totalAttended`, `attendBySmsReminder`, `total10MinPlus`, `total30MinPlus`, `totalBookings`, `totalCallsDatePassed`, `confirmed`, `shows`, `noShows`, `canceled`, `won`, `disqualified`, `qualified`, `leadQualityGreat`, `leadQualityOk`, `leadQualityBarelyPassable`, `leadQualityBadDq`, `avgProjectedDealSize`, `avgClosedDealValue`

### Notes on `accountsNeeded`

Source-fed from workbook values in v1 because the sheet uses mixed logic including `/300/7`, `/300/5`, `/100/5`, literals, and parent sums. Do not globally recompute.

## Derived Fields

All derived fields are computed in application code (`services/statistics.py`), not copied from workbook cells (which contain broken formulas in later rows).

### Zero-Safe Rule

All division operations return `null` when the denominator is zero or null. The frontend displays `null` as `—` (em dash).

### Delivery

| Field | Formula |
|-------|---------|
| `unsubPercent` | `unsubscribes / invited` |
| `ctrPercent` | `ghlPageViews / invited` |
| `lpRegPercent` | `lpRegs / ghlPageViews` |

### Yes

| Field | Formula |
|-------|---------|
| `yesPer1kInv` | `yesMarked / (invited / 1000)` |
| `yesPercent` | `yesMarked / invited` |
| `yesAttendPercent` | `yesAttended / yesMarked` |
| `yesStay10MinPercent` | `yes10MinPlus / yesAttended` |
| `yesAttendBySmsClickPercent` | `yesAttendBySmsClick / yesAttended` (zero-safe) |
| `yesBookingsPer1kInv` | `yesBookings / (invited / 1000)` |

### Maybe

| Field | Formula |
|-------|---------|
| `maybePer1kInv` | `maybeMarked / (invited / 1000)` |
| `maybeAttendPercent` | `maybeAttended / maybeMarked` |
| `maybeStay10MinPercent` | `maybe10MinPlus / maybeAttended` |
| `maybeAttendBySmsClickPercent` | `maybeAttendBySmsClick / maybeAttended` (zero-safe) |
| `maybeBookingsPer1kInv` | `maybeBookings / (invited / 1000)` |

### Self Reg

| Field | Formula |
|-------|---------|
| `selfRegPer1kInv` | `selfRegMarked / (invited / 1000)` |
| `selfRegAttendPercent` | `selfRegAttended / selfRegMarked` |
| `selfRegStay10MinPercent` | `selfReg10MinPlus / selfRegAttended` |
| `selfRegBookingsPer1kInv` | `selfRegBookings / (invited / 1000)` |

### Attendance

| Field | Formula |
|-------|---------|
| `invitedToRegPercent` | `totalRegs / invited` |
| `regToAttendPercent` | `totalAttended / totalRegs` |
| `invitedToAttendPercent` | `totalAttended / invited` |
| `totalAttendedPer1kInv` | `totalAttended / (invited / 1000)` |
| `attendBySmsReminderPercent` | `attendBySmsReminder / totalAttended` |
| `total10MinPlusPer1kInv` | `total10MinPlus / (invited / 1000)` |
| `attend10MinPercent` | `total10MinPlus / totalAttended` |
| `total30MinPlusPer1kInv` | `total30MinPlus / (invited / 1000)` |
| `attend30MinPercent` | `total30MinPlus / totalAttended` |

### Sales

| Field | Formula |
|-------|---------|
| `bookingsPerAttended` | `totalBookings / totalAttended` |
| `bookingsPerPast10Min` | `totalBookings / total10MinPlus` |
| `totalBookingsPer1kInv` | `totalBookings / (invited / 1000)` |
| `showPercent` | `shows / totalBookings` |
| `closeRatePercent` | `won / shows` (zero-safe) |
| `qualPercent` | `qualified / shows` (zero-safe) |

### Segment Name (display only)

```
segmentName = format(createdDate, "yyyy mmm dd") + ", " + industry + ", " + employeeRange + " employees, " + country
```

Returns `null` if any input field is missing.

## Null Display Rules

| Condition | API value | UI display |
|-----------|-----------|------------|
| Blank/empty source cell | `null` | `—` |
| Zero denominator in formula | `null` | `—` |
| Explicit numeric zero | `0` | `0` |
| Workbook `#DIV/0!` | `null` | `—` |

## Parent Aggregation Rules

Parent summary rows are **recomputed from child rows**, not copied from workbook parent-row formulas (which are broken in later webinars).

1. **Sum**: Most raw numeric metrics are summed across all children (including Nonjoiners and NO LIST DATA rows)
2. **Average**: `avgProjectedDealSize` — average of non-null child values
3. **Sum**: `avgClosedDealValue` — sum of non-null child values
4. **Sum**: `accountsNeeded` — sum of source-fed child values (not recomputed)
5. **Derive**: After aggregating raw counts, derived percentages/ratios are computed from the aggregated totals

## Workbook Anomalies

The following parent rows contain broken range references that spill into unrelated sections. This is why parent aggregation is semantic (sum children) rather than formula-copying:

- **W114, W115, W117**: Parent SUM formulas reference ranges beyond their child rows
- **W122**: `J153 = SUM(J154:J348)` — spills into webinars 123–136, producing `gcalInvited = 5,401,734` (correct value from rows 154–156 is `147,528`)
- **W136**: Parent row has stale/zeroed formulas; child rows 302–305 are valid but rows 306+ are scratch notes

## Future GoHighLevel Replacement Boundary

When GHL integration is added:

- **Changes**: `WorkbookMockStatisticsSource` is replaced with `GoHighLevelStatisticsSource` that fetches raw/source fields from the GHL API
- **Unchanged**: All derived metric formulas, parent aggregation logic, API response contract, frontend rendering, and this documentation
- The source adapter protocol in `services/statistics.py` defines the swap boundary
