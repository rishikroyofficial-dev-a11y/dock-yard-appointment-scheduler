# Data Dictionary

**Dataset:** Synthetic dock/yard appointment scheduling.
**Storage:** Operational entity CSV files plus separate labelled ground truth.
**Source of truth for code-facing fields:** `models.py`, `schema.py`, and `config.py`.

---

## Common Conventions

- **Date:** `YYYY-MM-DD`; **date/time:** `YYYY-MM-DDTHH:MM` (no timezone offset embedded).
- Booleans export as `1` or `0`; `None` exports as an empty cell.
- Primary keys (PK) are unique and non-null. Foreign keys (FK) must reference an existing parent when populated.
- `effective_to = NULL` means the master record remains valid.
- Required vs optional follows the dataclass field annotations, with additional status-specific rules in `validate.py`.
- The dirty dataset intentionally violates selected business rules but preserves documented structural integrity.

---

## Facility — `facilities.csv`  (PK: `facility_id`)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| facility_id | string | yes | `FAC-###`, unique |
| facility_name | string | yes | Non-empty, unique |
| city | string | yes | City name |
| timezone | string | yes | IANA zone; generated value `Asia/Kolkata` |
| open_hour | int | yes | 0–23, less than `close_hour` |
| close_hour | int | yes | 1–24, greater than `open_hour` |
| status | enum | yes | `ACTIVE`, `INACTIVE` |
| effective_from | date | yes | Start of validity |
| effective_to | date | no | If present, >= `effective_from` |

---

## Dock — `docks.csv`  (PK: `dock_id`; FK: `facility_id` → Facility, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| dock_id | string | yes | `DOCK-FAC-###-###`; embeds facility and number |
| facility_id | string | yes | FK to `facilities` |
| dock_number | int | yes | Unique per facility, positive |
| dock_type | enum | yes | `STANDARD`, `REEFER`, `HAZMAT_CERTIFIED` |
| dock_mode | enum | yes | `INBOUND`, `OUTBOUND`, `BOTH` |
| max_concurrent_trucks | int | yes | `1` in this model |
| status | enum | yes | `ACTIVE`, `INACTIVE` |
| effective_from / effective_to | date | yes / no | Validity interval |

---

## YardSlot — `yard_slots.csv`  (PK: `yard_slot_id`; FK: `facility_id` → Facility, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| yard_slot_id | string | yes | `YARD-FAC-###-###` |
| facility_id | string | yes | FK to `facilities` |
| slot_number | int | yes | Unique per facility |
| slot_type | enum | yes | `STANDARD`, `REEFER_PLUG` |
| status | enum | yes | `ACTIVE`, `INACTIVE` |
| effective_from / effective_to | date | yes / no | Validity interval |

---

## Carrier — `carriers.csv`  (PK: `carrier_id`)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| carrier_id | string | yes | `CAR-###` |
| carrier_name | string | yes | Unique name |
| scac_code | string | yes | Unique, four uppercase letters (synthetic) |
| status | enum | yes | `ACTIVE`, `INACTIVE` |
| effective_from / effective_to | date | yes / no | Validity interval |

---

## Vehicle — `vehicles.csv`  (PK: `vehicle_id`; FK: `carrier_id` → Carrier, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| vehicle_id | string | yes | `VEH-#####` |
| carrier_id | string | yes | FK to `carriers` |
| vehicle_type | enum | yes | `DRY_VAN`, `REEFER_TRUCK`, `TANKER`, `FLATBED` |
| plate_number | string | yes | Unique synthetic plate |
| is_refrigerated | bool | yes | `1` for `REEFER_TRUCK` |
| hazmat_certified | bool | yes | `1` for all `TANKER`; some dry vans also permitted |
| capacity_pallets | int | yes | Positive pallet capacity |
| status | enum | yes | `ACTIVE`, `INACTIVE` |
| effective_from / effective_to | date | yes / no | Validity interval |

---

## LaborShift — `labor_shifts.csv`  (PK: `shift_id`; FK: `facility_id` → Facility, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| shift_id | string | yes | `SHIFT-FAC-###-YYYY-MM-DD-[AB]` |
| facility_id | string | yes | FK to `facilities` |
| shift_date | date | yes | Inside configured window |
| shift_code | enum | yes | `A`, `B`; unique per facility and date |
| start_time / end_time | string | yes | `HH:MM`; `start_time` < `end_time` |
| crews_available | int | yes | Crew count; at least `MIN_CREWS` in generator |
| status | enum | yes | `SCHEDULED`, `CANCELLED` |

---

### Labor Availability and Anomaly Semantics

Each scheduled labor shift provides a configured number of
crews. A cancelled shift contributes zero usable crews.

The clean allocator checks labor availability before
scheduling appointments.

The `LABOR_SHIFT_UNAVAILABLE` anomaly cancels an existing
shift after appointments have been allocated.

The current detector flags appointments overlapping a
cancelled shift. This does not independently establish
that all alternative labor capacity is unavailable.

---

## DockCalendar — `dock_calendar.csv`  (PK: `calendar_id`; FK: `dock_id` → Dock, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| calendar_id | string | yes | `CAL-<dock_id>-YYYYMMDD` |
| dock_id | string | yes | FK to `docks` |
| calendar_date | date | yes | One row per dock and date |
| open_time / close_time | string | yes | `HH:MM`; `open_time` < `close_time` |
| status | enum | yes | `OPEN`, `MAINTENANCE` |
| available_minutes | int | yes | `(close − open) × 60` if `OPEN`; else `0` |

---

## HandlingRequirement — `handling_requirements.csv`  (PK: `handling_req_id`; reference data)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| handling_req_id | string | yes | `HR-###` |
| requirement_code | string | yes | Unique descriptive code |
| description | string | yes | Handling description |
| category | enum | yes | `LOAD_CLASS`, `ADD_ON` |
| load_type | enum | no | `AMBIENT`, `REFRIGERATED`, `HAZARDOUS`; null for add-ons |
| fixed_minutes | int | yes | Fixed service minutes, >= 0 |
| minutes_per_pallet | float | yes | Minutes per pallet, >= 0 |
| temp_min_c / temp_max_c | int | no | Applicable to refrigerated handling; `min < max` |

---

## Appointment — `appointments.csv`  (PK: `appointment_id`; FKs: `facility_id`, `carrier_id`, `vehicle_id`, `dock_id`, `yard_slot_id`)

`dock_id`, `yard_slot_id`, `scheduled_start` and `scheduled_end` are empty until the allocator runs. Empty for `REJECTED` appointments.

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| appointment_id | string | yes | `APPT-2026-######` |
| facility_id | string | yes | FK to `facilities` |
| carrier_id | string | yes | FK to `carriers` |
| vehicle_id | string | yes | FK to `vehicles`; must belong to carrier and meet load compatibility |
| direction | enum | yes | `INBOUND`, `OUTBOUND` |
| load_type | enum | yes | `AMBIENT`, `REFRIGERATED`, `HAZARDOUS` |
| request_created_at | datetime | yes | Earlier than `requested_start` |
| requested_start | datetime | yes | Original carrier request; 30-minute grid; never overwritten by scheduling |
| total_pallets | int | yes | DERIVED: sum of linked shipment pallets |
| planned_duration_minutes | int | yes | DERIVED: sum of shipment service minutes rounded up to 30-minute grid |
| status | enum | yes | `REQUESTED`, `SCHEDULED`, `CHECKED_IN`, `AT_DOCK`, `SERVICED`, `COMPLETED`, `NO_SHOW`, `CANCELLED`, `REJECTED` |
| dock_id | string | no | FK to `docks`; populated for allocated appointments |
| yard_slot_id | string | no | FK to `yard_slots`; populated for allocated appointments |
| scheduled_start / scheduled_end | datetime | no | Allocated time; `end − start = planned_duration_minutes`; same day, inside dock open hours |

> The allocator also enforces non-overlapping vehicle reservations for clean scheduled data.
> `(vehicle_id, requested_start)` is not a required natural unique key: multiple carrier requests
> may legitimately seek the same time.

---

## Shipment — `shipments.csv`  (PK: `shipment_id`; FK: `appointment_id` → Appointment, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| shipment_id | string | yes | `SHP-2026-######` |
| appointment_id | string | yes | FK to `appointments` |
| load_type | enum | yes | Matches appointment `load_type` |
| pallets | int | yes | >= 2 |
| weight_kg | int | yes | Positive integer kilograms |
| service_minutes | int | yes | DERIVED: ceil of sum over linked handling requirements of `fixed + per_pallet × pallets` |
| status | enum | yes | `PLANNED`, `COMPLETED`, `NOT_HANDLED` (derived from appointment outcome) |

---

## ShipmentHandling — `shipment_handling.csv`  (composite PK: `shipment_id` + `handling_req_id`)

Bridge table for the Shipment ↔ HandlingRequirement many-to-many relationship.

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| shipment_id | string | yes | FK to `shipments` |
| handling_req_id | string | yes | FK to `handling_requirements` |

Each shipment has exactly one matching `LOAD_CLASS` requirement and may have optional `ADD_ON` requirements.

---

## CheckInEvent — `checkin_events.csv`  (PK: `event_id`; FK: `appointment_id` → Appointment, N:1)

Append-only lifecycle log. Rows are only added, never edited (except for the `CHECKIN_BEFORE_DATE` and `NO_SHOW_NOT_RECORDED` anomalies in `anomalies.py`).

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| event_id | string | yes | `CHECK-<appointment_id>-NN` |
| appointment_id | string | yes | FK to `appointments` |
| event_seq | int | yes | Per-appointment sequence `1..n`, no gaps |
| event_type | enum | yes | `SCHEDULED`, `REJECTED`, `CHECKED_IN`, `DOCK_STARTED`, `DOCK_COMPLETED`, `DEPARTED`, `NO_SHOW` |
| from_status | enum | no | Previous appointment status; all generated events specify it |
| to_status | enum | yes | New appointment status after this event |
| event_time | datetime | yes | Strictly increasing by `event_seq` per appointment |
| source | enum | yes | `ALLOCATOR`, `GATE`, `DOCK_OPS` |

---

## Exception — `exceptions.csv`  (PK: `exception_id`; FK: `appointment_id` → Appointment, N:1)

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| exception_id | string | yes | `EXC-2026-######` |
| appointment_id | string | yes | FK to `appointments` |
| exception_type | enum | yes | `SLOT_SHIFTED`, `UNSCHEDULABLE`, `NO_SHOW`, `EARLY_ARRIVAL`, `CONGESTION_DELAY` |
| cause_code | enum | yes | `DOCK_CAPACITY_FULL`, `LABOR_SHORTAGE`, `DOCK_MAINTENANCE`, `OUTSIDE_OPERATING_HOURS`, `YARD_FULL`, `NO_WINDOW_IN_HORIZON`, `NO_SHOW`, `EARLY_ARRIVAL`, `DOCK_STILL_OCCUPIED` |
| severity | enum | yes | `LOW`, `MEDIUM`, `HIGH` |
| detected_at | datetime | yes | Detection timestamp |
| delay_minutes | int | no | Minutes; meaning depends on exception type |
| details | string | yes | Human-readable explanation |

---

## GroundTruth — `ground_truth/ground_truth.csv` and `.json`  (PK: `issue_id`)

Kept in a separate folder and never joined into the 13 operational tables. Not read by `validate.py`.

| Field | Type | Required | Definition / rule |
|---|---|---|---|
| issue_id | string | yes | `GT-######`, unique |
| issue_type | enum | yes | `DOCK_OVERLAP`, `INCOMPATIBLE_LOAD`, `CHECKIN_BEFORE_DATE`, `LABOR_SHIFT_UNAVAILABLE`, `NO_SHOW_NOT_RECORDED` |
| table_name | string | yes | Table containing the changed or affected record |
| record_id | string | yes | Primary key of the directly changed or affected record |
| related_record_id | string | no | Related appointment, shift, or omitted-event ID |
| field_name | string | yes | Changed or implicated field |
| original_value | string | no | Value before injection, where meaningful |
| injected_value | string | no | Value after injection, where meaningful |
| detection_rule | string | yes | Plain-language rule a validator can apply |

> A root-cause change can produce several ground-truth entries, including affected-appointment rows
> that were not directly edited. For the labor case, evaluate appointment-level entries separately
> from root-shift entries.

---

## Relationships

| Relationship | Cardinality |
|---|---|
| Facility → Dock / YardSlot / LaborShift | 1:N, mandatory |
| Dock → DockCalendar | 1:N (one row per day) |
| Carrier → Vehicle | 1:N, mandatory |
| Facility → Appointment | 1:N |
| Carrier → Appointment | 1:N |
| Vehicle → Appointment | 1:N; vehicle intervals must not overlap |
| Dock → Appointment | 1:N; optional until allocation |
| YardSlot → Appointment | 1:N; optional until allocation |
| Appointment → Shipment | 1:N; at least one shipment per appointment |
| Shipment ↔ HandlingRequirement | N:M via `ShipmentHandling` bridge table |
| Appointment → CheckInEvent | 1:N, append-only lifecycle history |
| Appointment → Exception | 1:N, optional |

---

## Appointment Lifecycle

| From | Event | To | Source |
|---|---|---|---|
| `REQUESTED` | `SCHEDULED` | `SCHEDULED` | `ALLOCATOR` |
| `REQUESTED` | `REJECTED` | `REJECTED` | `ALLOCATOR` |
| `SCHEDULED` | `CHECKED_IN` | `CHECKED_IN` | `GATE` |
| `SCHEDULED` | `NO_SHOW` | `NO_SHOW` | `GATE` |
| `CHECKED_IN` | `DOCK_STARTED` | `AT_DOCK` | `DOCK_OPS` |
| `AT_DOCK` | `DOCK_COMPLETED` | `SERVICED` | `DOCK_OPS` |
| `SERVICED` | `DEPARTED` | `COMPLETED` | `GATE` |

`SCHEDULED → CANCELLED` is a legal transition in `config.py` but the current simulator does not generate cancellations.
