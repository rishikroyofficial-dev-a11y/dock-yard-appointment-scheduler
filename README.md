# Dock & Yard Appointment Scheduling — Synthetic Logistics Simulator

A deterministic Python project that creates synthetic logistics data, assigns dock appointments
using capacity and compatibility rules, simulates operational events, injects labelled anomalies,
and evaluates rule-based findings.

> **Scope:** A synthetic-data simulator and evaluation pipeline, not a production warehouse
> management system. All operational records are synthetic.

---

## Quick Start

Run these commands from the repository root, where `main.py` is located. The implementation uses
the Python standard library (`sqlite3`, `csv`, `dataclasses`, etc.); `pandas` is not required.

```bash
python --version

# Starter scale — clean baseline
python main.py --scale starter --no-anomalies --out output_clean
python validate.py --scale starter --out output_clean

# Starter scale — with injected anomalies
python main.py --scale starter --out output_dirty
python validate.py --scale starter --out output_dirty
python evaluate.py --scale starter --out output_dirty
```

**Full scale:**

```bash
python main.py --scale full --seed 20261022 --no-anomalies --out output_full_clean
python validate.py --scale full --out output_full_clean

python main.py --scale full --seed 20261022 --out output_full_dirty
python validate.py --scale full --out output_full_dirty
python evaluate.py --scale full --out output_full_dirty
```

> `evaluate.py` requires `validation/findings.json`, so run `validate.py` before it.
> The validator returns exit code `1` if a must-pass check fails; inspect the report before evaluating.

---

## Dataset Configurations

| Configuration       | Starter | Full   |
|---------------------|---------|--------|
| Facilities          | 2       | 10     |
| Docks per facility  | 5       | 10     |
| Total docks         | 10      | 100    |
| Appointments        | 200     | 20,000 |
| Days                | 7       | 60     |

Default seed: `20261022`. Simulation window begins `2026-08-01`.

---

## Architecture

| File | Role |
|------|------|
| `config.py` | Rules, distributions, seed and scales |
| `models.py` + `schema.py` | Dataclasses, tables, keys, relationships, allowed values |
| `ids.py` | Deterministic record identifiers |
| `master_data.py` + `calendars.py` | Facility / dock / yard / carrier / vehicle masters; labor shifts and dock calendars |
| `demand.py` | Appointment requests, shipments, handling requirements and service durations |
| `allocator.py` | First-come-first-served scheduling, earliest feasible 30-minute slot; dock, yard, labor and vehicle occupancy |
| `events.py` + `simulator.py` | Lifecycle events, simulated check-in / service / departure, operational exceptions |
| `anomalies.py` | Intentional post-baseline data corruption and ground-truth labels |
| `export.py` | Deterministic CSV output and SHA-256 hashing |
| `metrics.py` | Operational KPIs from appointments / events / calendars |
| `validate.py` | SQL-backed data checks and rule detectors; does not read ground truth |
| `evaluate.py` | Compares saved detector findings against separately exported ground truth |
| `main.py` | Command-line pipeline entry point |

---

## Scheduling and Event Rules

Requests are processed in request-creation order. The allocator searches up to `MAX_SHIFT_DAYS`
beyond the requested time, checking:

- compatible dock type and direction
- open dock calendar
- non-overlapping dock reservation
- available labor crew
- suitable yard space
- non-overlapping vehicle reservation

Among feasible docks it selects the least-booked one. Requests without a feasible slot are rejected.

The simulator creates check-in, dock start/completion and departure events. No-shows, early arrivals
and congestion outcomes arise from explicit simulation rules, not independent random labels.

---

## Five Deliberate Anomaly Classes

| Anomaly type | What is broken |
|---|---|
| `DOCK_OVERLAP` | Two appointments share a dock at the same time |
| `INCOMPATIBLE_LOAD` | Load assigned to an incompatible dock type or vehicle |
| `CHECKIN_BEFORE_DATE` | Check-in event dated before the appointment date |
| `LABOR_SHIFT_UNAVAILABLE` | Appointment overlaps a cancelled labor shift |
| `NO_SHOW_NOT_RECORDED` | No-show occurred but no event or exception was written |

Ground truth is stored separately in `ground_truth/` and never joined to operational input files.
One injected root cause can affect multiple records; see [`docs/decisions.md`](decisions.md).

---

## Validation and Measured Results

Observed in development runs (seed `20261022`):

| Run | Observation |
|-----|-------------|
| Clean starter | 24/24 must-pass checks; B01–B05 all zero |
| Dirty starter | 24/24 must-pass checks; all five detector classes found cases |
| Dirty full | 24/24 must-pass checks |
| Full anomaly evaluation | 40 injected and 40 found in each of five classes; precision/recall 100% |
| Repeatability | 16/16 exported CSV/JSON files had matching SHA-256 hashes across two identical full-scale runs |

> **Evaluation caveat:** Metrics are from the project's own label-matching rules, not an
> independently audited benchmark. The dock-overlap evaluator matches a detected pair if it
> contains an injected appointment; inspect `evaluate.py` before interpreting the percentages
> as strict pair-level precision. The labor detector checks overlap with a `CANCELLED` shift
> and is not a general-purpose residual labor-capacity evaluator.

**To repeat the reproducibility check:**

```bash
python main.py --scale full --seed 20261022 --out reproducibility_run1
python main.py --scale full --seed 20261022 --out reproducibility_run2
```

Use `Get-FileHash -Algorithm SHA256` (PowerShell) or `sha256sum` (Linux/macOS) to compare
corresponding files in the two `full/` directories. Only generator outputs were compared;
validation-report hashes were not part of the 16-file result.

---

## Outputs

`main.py` writes:
- 13 operational CSV tables
- `kpi_summary.json`
- `ground_truth/ground_truth.csv` and `.json` (when anomaly injection is enabled)

`validate.py` writes:
- `validation/validation_summary.json`
- `validation/findings.json`

`evaluate.py` writes:
- `validation/evaluation.json`

> **Current export scope:** All operational entities are exported as CSV. A general SQL seed
> exporter has not been included. Do not claim SQL exports unless added and tested.

---

## Project Documentation

- [`docs/data_dictionary.md`](data_dictionary.md) — column-level definitions and relationships
- [`docs/decisions.md`](decisions.md) — assumptions, trade-offs and known limitations
- [`docs/ai_prompt_log.md`](ai_prompt_log.md) — AI tool and prompt disclosure

---

## Limitations

- No live GPS or travel-time constraints.
- No production operational integrations.
- Yard occupancy is a fixed pre-dock hold; labor is modelled as crews per slot.
- Events use timestamp strings without timezone offsets; generated facilities use `Asia/Kolkata`.
  Changing facility timezones requires explicit timezone handling.
- Simulated physical dock activity can extend beyond planned time windows.

See [`docs/decisions.md`](decisions.md) for additional limitations and test interpretations.

---

## Reproducibility and Provenance

All dataset records are synthetic. Random streams are seeded per stage via
`random.Random(f"{seed}:{stage}")`. Keep the seed and generator version fixed when comparing
checksums.