# AI-Assisted Development — Prompt Log

**Project:** Dock and Yard Appointment Scheduling Simulator
**Tool:** ChatGPT
**Record type:** Professionally written development requests (original verbatim prompt transcripts)

> This log covers the topics and decisions I worked through with an AI tool during development.
> Each entry represents a distinct phase of the project, from initial design through to submission
> preparation. Prompts are summarised professionally rather than copied verbatim, in line with the
> FAQ guidance that AI responses are optional and confidential assessment content must not be
> published.

---

## Development Prompts

### 01. Technology Selection and Implementation Approach

Provide a maintainable approach for building a deterministic synthetic logistics-data generator
using Python's standard library. Explain implementation trade-offs and avoid unnecessary
dependencies such as pandas.

### 02. Domain Modeling and Referential Integrity

Review the relational model for facilities, docks, yard slots, carriers, vehicles, labor shifts,
appointments, shipments, handling requirements, lifecycle events, and exceptions. Validate primary
keys, foreign keys, and relationship cardinalities.

### 03. Data Dictionary and Schema Alignment

Evaluate the data dictionary against the Python dataclasses and schema definitions. Identify
inconsistencies in field types, required attributes, enumerations, validation constraints, and
identifier formats.

### 04. Modular Architecture and Pipeline Integration

Assess the integration of master-data generation, operational calendars, demand creation,
appointment allocation, event simulation, anomaly injection, export, validation, and evaluation
through the main command-line runner.

### 05. Constraint-Aware Appointment Allocation

Review appointment scheduling logic for compatible docks, operating hours, labor capacity,
yard-slot availability, shipment requirements, and mutually exclusive vehicle reservations.
Identify potential resource conflicts and propose targeted fixes.

### 06. Lifecycle Event Modeling

Review the appointment state machine and event-log implementation for legal status transitions,
timestamp ordering, consistent event sequences, and traceable exception records.

### 07. Runtime Debugging and Interface Consistency

Diagnose Python runtime failures caused by mismatched return types, inconsistent module
interfaces, or invalid data access. Recommend minimal corrections that preserve the established
architecture.

### 08. Structural and Business-Rule Validation

Design and review SQLite-backed data-integrity checks for primary keys, foreign keys,
natural-key constraints, enum values, chronology, resource availability, and clean-baseline
consistency.

### 09. Anomaly Injection and Ground-Truth Tracking

Review deterministic injection of dock overlaps, incompatible loads, check-ins before the
appointment date, unavailable labor shifts, and unrecorded no-shows. Ensure affected records and
root causes are traceable in a separate ground-truth dataset.

### 10. Independent Detection and Evaluation

Evaluate rule-based anomaly detectors against labeled ground truth using per-type precision,
recall, and detection counts. Examine potential false positives, false negatives, and the
limitations of record-level matching.

### 11. Reproducibility and Scale Testing

Develop an end-to-end verification procedure for starter and full-scale generation, clean and
anomaly-injected datasets, deterministic seeds, repeatable output hashes, and validation results.

### 12. Submission Readiness Assessment

Review implemented features against the assessment deliverables. Identify missing artifacts,
undocumented limitations, integration risks, and final execution checks required before
submission.

### 13. Technical Documentation Review

Improve the README, data dictionary, and design-decisions document to reflect implemented
behavior, resource constraints, reproducibility procedures, known limitations, and observed
results.

### 14. Repository Preparation and Publication

Prepare a public GitHub repository with a clear source layout, suitable `.gitignore`, reproducible
setup instructions, and the required documentation. Provide a step-by-step browser-based upload
and verification workflow.

---

## What I Personally Reviewed and Validated

- Read and understood every module before including it: `config.py`, `ids.py`, `models.py`,
  `master_data.py`, `calendars.py`, `demand.py`, `allocator.py`, `events.py`, `simulator.py`,
  `anomalies.py`, `export.py`, `metrics.py`, `validate.py`, `evaluate.py`, `schema.py`.
- Ran the generator at both starter and full scale and inspected the CSV output directly.
- Verified that two full-scale runs with the same seed produced byte-identical files.
- Checked the validation report (`validation_summary.json`) and confirmed 24/24 must-pass checks
  on both the clean and dirty datasets.
- Reviewed the ground-truth file and confirmed that the five anomaly types were detected with
  100% precision and recall under the project's matching rules.
- Understood the key design decisions documented in `docs/decisions.md` and can explain them:
  why derived values are computed from source records, why the baseline is generated before
  anomalies are injected, why IDs are deterministic and child IDs embed their parent, and why
  independent random streams are used per stage.

## Where I Relied Heavily on AI Assistance

- Initial module structure and the first working versions of `allocator.py`, `simulator.py`,
  `validate.py`, and `anomalies.py`.
- Debugging interface mismatches between modules (covered in prompt 07).
- Drafting the data dictionary, decisions document, and README structure, which I then reviewed
  and revised.

## Where AI Accelerated My Work

- Translating business rules (compatibility, lifecycle, anomaly injection) into Python quickly,
  so more time could be spent on understanding and validating the output rather than writing
  boilerplate.
- Structuring the SQLite-backed validation checks (prompt 08) and the independent evaluation
  script (prompt 10).