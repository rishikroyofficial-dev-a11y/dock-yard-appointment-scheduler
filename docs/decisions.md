# Decisions, Assumptions and Limitations

---

## Project Overview

This project generates reproducible synthetic data for dock and yard appointment scheduling.
A rule-based allocator assigns appointment requests to feasible slots, and a simulator derives
lifecycle events and operational exceptions from documented rules rather than assigning outcome
labels at random.

Operational data is exported to CSV. Validation uses an in-memory SQLite database, while anomaly
labels are stored separately in ground-truth CSV and JSON files.

---

## Assumptions

**1. Identifiers.**
IDs are deterministic and zero-padded. `DOCK-FAC-001-001` identifies a dock belonging to `FAC-001`;
`CHECK-APPT-2026-000001-01` identifies an appointment lifecycle event. All other identifier formats
are defined in `ids.py`.

**2. Simulation window.**
The full dataset spans 60 days beginning on `2026-08-01`. Facilities operate from 06:00 to 22:00,
except Sundays (08:00–16:00). All generated facilities use `Asia/Kolkata`; exported timestamps have
no embedded timezone offset.

**3. Dock and labor capacity.**
Each dock serves at most one scheduled appointment at a time. One labor crew supports one dock
appointment; `crews_available` limits parallel work. A cancelled shift contributes no crews during
its interval.

**4. Yard occupancy.**
A truck reserves a compatible yard slot for the 60 minutes preceding its scheduled dock start.
Refrigerated loads require a `REEFER_PLUG` yard slot. No separate yard-slot calendar is generated.
Yard slots are subject to modelled occupancy rather than being unlimited.

**5. Compatibility.**
Refrigerated loads require `REEFER` docks; hazardous loads require `HAZMAT_CERTIFIED` docks.
Ambient loads prefer `STANDARD` docks, with compatible specialised docks permitted after the
configured overflow delay of 120 minutes.

**6. Vehicle reservations.**
The clean allocator prevents a vehicle from being assigned to overlapping scheduled appointments.
A requested time is not itself a unique vehicle booking: requests may compete for the same vehicle
and are resolved during scheduling.

**7. Entity naming.**
`CheckInEvent` stores all appointment lifecycle events, not only check-ins. The Python class
`ExceptionRecord` is exported to `exceptions.csv`, avoiding a collision with Python's built-in
`Exception`.

**8. Request versus schedule.**
`requested_start` is never overwritten. Successful allocation populates `scheduled_start`,
`scheduled_end`, `dock_id`, and `yard_slot_id`. `Appointment.status` represents the current
state; `checkin_events.csv` contains its recorded history.

**9. Dataset and anomaly scope.**
Synthetic records and ground-truth labels follow the stated simulation rules. The deliberately
corrupted dataset is distinct from the clean baseline and is intended for controlled evaluation
of specific business-rule detectors.

---

## Key Design Decisions

- **Standard-library Python and SQLite.** Core generation, scheduling, simulation, export, and
  evaluation run without pandas. SQLite is used to query and validate exported CSV records, not
  as the primary persisted generator output.

- **Independent seeded random streams.** Each generation stage uses a stream such as
  `random.Random(f"{seed}:demand")`, limiting cross-stage changes in random choices when
  implementation details change.

- **Parent-before-child generation.** Facilities, carriers, docks, yard slots, and vehicles are
  generated before dependent appointments, shipments, and events, preserving referential integrity.

- **Derived measures.** Shipment service times come from handling requirements; appointment
  durations and pallet totals come from shipments rather than independently sampled totals.

- **Earliest-feasible allocation.** Requests are processed in booking order. The allocator checks
  dock compatibility and occupancy, labor capacity, yard-slot occupancy, vehicle availability, and
  the scheduling horizon. It chooses the least-booked eligible dock among those available at the
  earliest feasible start.

- **Peak-day selection.** Peak-demand days are sampled from Monday through Friday to produce
  meaningful peak scenarios.

- **Clean baseline before corruption.** Anomalies are injected only after scheduling and
  operational simulation have completed. The ground truth is exported separately from operational
  data.

- **Explicit lifecycle history.** Events record transitions such as scheduling, check-in, dock
  start, service completion, and departure. The normal simulation appends events; anomaly injection
  intentionally alters or removes selected records.

---

## Simulation Rules

Implemented in `simulator.py` with parameters from `config.py`.

| Rule | Detail |
|---|---|
| No-show probability | Each carrier receives a synthetic rate between 1% and 8%; no-shows are recorded 60 minutes after the scheduled start |
| Early arrivals | ~12% of trucks arrive 30–150 minutes early; all others follow Normal(−3, 12 min) clipped to [−25, +45] |
| Early-arrival exception | Arrivals ≥ 30 minutes early generate an `EARLY_ARRIVAL` exception |
| Dock start | Latest of: scheduled start, check-in + 5–20 min gate move, previous truck's dock completion |
| Congestion exception | Previous truck blocks a ready truck for ≥ 30 minutes → `CONGESTION_DELAY` with cause `DOCK_STILL_OCCUPIED` |
| Actual service time | Planned service minutes × Triangular(0.85, 1.35, mode 1.0) |
| Departure | 5–30 minutes after service completion |
| Wait time | Measured from `CHECKED_IN` to `DOCK_STARTED`; includes any early-arrival wait for the slot |

---

## Deliberate Anomaly Injection

`anomalies.py` introduces five anomaly classes after the baseline has been generated. At full scale,
each class targets approximately 0.2% of appointments (40 cases per class), subject to eligible
candidates.

| Anomaly | Injected scenario | Detector's interpretation |
|---|---|---|
| `DOCK_OVERLAP` | Assign one appointment to a compatible dock already occupied during the same interval | Two scheduled appointments overlap on a capacity-one dock |
| `INCOMPATIBLE_LOAD` | Assign an unsuitable dock or a vehicle lacking required load capabilities | Assigned dock or vehicle is incompatible with the load |
| `CHECKIN_BEFORE_DATE` | Move a `CHECKED_IN` event to the previous calendar day | Check-in date precedes the appointment's scheduled date |
| `LABOR_SHIFT_UNAVAILABLE` | Cancel a shift that has overlapping scheduled appointments | Appointments overlap a cancelled labor shift |
| `NO_SHOW_NOT_RECORDED` | Remove no-show event and exception; restore appointment and shipments to stale states | Appointment remains scheduled after its slot without check-in or no-show history |

> An anomaly may affect more than one record. Ground-truth records distinguish root-cause changes
> from affected appointments. The labor detector identifies overlap with a cancelled shift; it does
> not independently prove that no alternative aggregate labor capacity was available.

---

## Verification Performed

| Check | Result |
|---|---|
| Clean starter: must-pass checks | 24/24 passed; B01–B05 all zero findings |
| Dirty starter: must-pass checks | 24/24 passed; all five anomaly types detected |
| Dirty full: must-pass checks | 24/24 passed |
| Full anomaly evaluation | 40 detected / 40 labelled per type; precision and recall 100% under implemented matching rules |
| Reproducibility | Two full-scale runs with seed `20261022` produced identical SHA-256 hashes for all 16 compared CSV/JSON files |

> These are results of the project's own validator and evaluator, not external benchmark results.
> The dock-overlap evaluator treats a detected pair as a match when it contains a labelled
> appointment; it is not an independent, pair-exact benchmark. The clean full-scale validation
> total should be documented separately if confirmed in the final run.

---

## Known Limitations and Trade-offs

- **Finite horizon.** Requests near the end of the 60-day window can be rejected because their
  feasible allocation would fall outside that window, not necessarily because warehouse capacity
  is fundamentally insufficient.

- **Simplified yard model.** Yard positions are reserved for a fixed pre-dock holding period;
  yard arrivals, departures, and separate maintenance calendars are not fully modelled.

- **Simplified transport model.** Vehicle conflicts are checked against scheduled intervals, but
  travel time between facilities, repositioning, and real-world journey feasibility are not
  simulated.

- **Discrete scheduling.** Planned appointments use 30-minute slots. Actual operational event
  times can occur between those slots.

- **Recorded and actual operations differ.** The simulator accounts for delays caused by earlier
  trucks, but is not a live warehouse management system.

- **Anomaly detector scope.** `LABOR_SHIFT_UNAVAILABLE` checks cancelled-shift overlaps rather
  than recalculating all possible replacement labor capacity. Ground-truth evaluation uses
  project-specific matching rules.

- **Anomaly side effects.** `NO_SHOW_NOT_RECORDED` intentionally removes historical records and
  changes related statuses. Immutable exception IDs may therefore have gaps. In ordinary
  simulation, event history is append-only.

- **No generated appointment cancellations.** `SCHEDULED → CANCELLED` is a legal transition in
  `config.py` but is not currently generated by the simulator.

- **Output size.** Event volume depends on the proportions of completed, rejected, and no-show
  appointments and may fall below the suggested approximate target of 100,000 events.

- **Metric interpretation.** KPIs are calculated from the exported dataset, so deliberately
  injected anomalies may affect them. Use `--no-anomalies` for clean-baseline measurements.

---

## Results to Refresh Before Submission

Earlier exploratory runs produced specific rejection counts, shift percentages, event totals, and
wait-time averages. Those figures may have changed after adding vehicle availability to the
allocator and modifying anomaly injection. Only add exact numerical claims after checking the
latest `kpi_summary.json`, generation output, and validation reports.