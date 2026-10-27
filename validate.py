"""validate.py - Step 8. Loads the exported CSVs into an in-memory SQLite database and checks them.

Two kinds of check:
  must_pass  structure, keys, enums, ordering, reconciliation, lifecycle, capacity. Expected 0 violations on
             ANY dataset (clean or with injected anomalies - the anomalies are semantic, not structural).
  detector   the five business rules the anomalies break. Violations here are FINDINGS (0 on a clean baseline).

This script never reads the ground truth. evaluate.py compares its findings to the ground truth afterwards.
Usage: python validate.py --scale full --out output
"""
import argparse
import csv
import dataclasses
import json
import math
import os
import re
import sqlite3
import sys
import typing
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import ids
from config import LEGAL_TRANSITIONS, COMPATIBLE_DOCKS, SLOT_MINUTES
from demand import FMT
from schema import (TABLES, PRIMARY_KEYS, FOREIGN_KEYS, ID_KIND, ENUMS, NATURAL_KEYS, EVENT_TO_STATUS)


# ------------------------------------------------------------------ loading
def _unwrap(tp):
    if typing.get_origin(tp) is typing.Union:
        return [a for a in typing.get_args(tp) if a is not type(None)][0], True
    return tp, False


def load_db(data_dir):
    conn = sqlite3.connect(":memory:")
    optional = {}
    for name, cls in TABLES.items():
        cols = []
        for f in dataclasses.fields(cls):
            tp, opt = _unwrap(f.type)
            cols.append((f.name, {str: "TEXT", int: "INTEGER", float: "REAL", bool: "INTEGER"}[tp], opt))
            optional[(name, f.name)] = opt
        conn.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t, _ in cols)})")   # no constraints: we TEST them
        with open(os.path.join(data_dir, f"{name}.csv"), newline="", encoding="utf-8") as fh:
            rows = []
            for r in csv.DictReader(fh):
                rows.append([None if r[c] == "" else (int(r[c]) if t == "INTEGER" else float(r[c]) if t == "REAL" else r[c])
                             for c, t, _ in cols])
        conn.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", rows)
    return conn, optional


def mins(a, b):      # SQL: minutes from timestamp a to timestamp b
    return f"CAST(ROUND((julianday({b}) - julianday({a})) * 1440) AS INTEGER)"


# ------------------------------------------------------------------ report
class Report:
    def __init__(self):
        self.results, self.findings = [], {}

    def add(self, check_id, kind, description, offenders, detail=None):
        offenders = sorted(set(map(str, offenders)))
        self.results.append({"id": check_id, "kind": kind, "description": description,
                             "violations": len(offenders), "sample": offenders[:5], **({"detail": detail} if detail else {})})


def run(conn, optional):
    Q = lambda sql: conn.execute(sql).fetchall()
    col = lambda sql: [r[0] for r in Q(sql)]
    rep = Report()
    MP = "must_pass"

    # ---- S01 primary keys unique and not null
    off, det = [], {}
    for t, pk in PRIMARY_KEYS.items():
        cols = ", ".join(pk)
        bad = col(f"SELECT {cols} FROM {t} WHERE " + " OR ".join(f"{c} IS NULL" for c in pk))
        bad += col(f"SELECT {pk[0]} FROM {t} GROUP BY {cols} HAVING COUNT(*) > 1")
        if bad: det[t] = len(bad)
        off += [f"{t}:{b}" for b in bad]
    rep.add("S01", MP, "Primary keys are unique and not null (all 13 tables)", off, det)

    # ---- S02 ID format
    off = []
    for t, kind in ID_KIND.items():
        off += [f"{t}:{v}" for v in col(f"SELECT {PRIMARY_KEYS[t][0]} FROM {t}") if not ids.is_valid(kind, v)]
    rep.add("S02", MP, "Every primary key matches its ID pattern (FAC-001, DOCK-FAC-001-001, APPT-2026-000001, ...)", off)

    # ---- S03 IDs embed their parent / counter consistently
    embeds = {"docks": ("dock_id", "'DOCK-' || facility_id || '-' || printf('%03d', dock_number)"),
              "yard_slots": ("yard_slot_id", "'YARD-' || facility_id || '-' || printf('%03d', slot_number)"),
              "checkin_events": ("event_id", "'CHECK-' || appointment_id || '-' || printf('%02d', event_seq)"),
              "labor_shifts": ("shift_id", "'SHIFT-' || facility_id || '-' || shift_date || '-' || shift_code"),
              "dock_calendar": ("calendar_id", "'CAL-' || dock_id || '-' || replace(calendar_date, '-', '')")}
    off = []
    for t, (pk, expr) in embeds.items():
        off += [f"{t}:{v}" for v in col(f"SELECT {pk} FROM {t} WHERE {pk} != {expr}")]
    rep.add("S03", MP, "Child IDs embed their parent ID / counter exactly (dock, yard slot, check-in event, shift, calendar)", off)

    # ---- S04 foreign keys
    off, det = [], {}
    for ct, cc, pt, pc in FOREIGN_KEYS:
        bad = col(f"SELECT c.{cc} FROM {ct} c LEFT JOIN {pt} p ON c.{cc} = p.{pc} WHERE c.{cc} IS NOT NULL AND p.{pc} IS NULL")
        if bad: det[f"{ct}.{cc}->{pt}"] = len(bad)
        off += [f"{ct}.{cc}:{b}" for b in bad]
    rep.add("S04", MP, f"Foreign keys all resolve to an existing parent ({len(FOREIGN_KEYS)} relationships)", off, det)

    # ---- S05 required fields present
    off = []
    for t, cls in TABLES.items():
        for f in dataclasses.fields(cls):
            if not optional[(t, f.name)]:
                n = Q(f"SELECT COUNT(*) FROM {t} WHERE {f.name} IS NULL")[0][0]
                if n: off.append(f"{t}.{f.name} ({n} nulls)")
    rep.add("S05", MP, "Required (non-optional) fields are never empty", off)

    # ---- S06 allowed values
    off = []
    for (t, c), allowed in ENUMS.items():
        marks = ",".join("?" * len(allowed))
        off += [f"{t}.{c}={v}" for (v,) in conn.execute(f"SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL AND {c} NOT IN ({marks})", allowed)]
    rep.add("S06", MP, f"Enumerated columns hold only allowed values ({len(ENUMS)} columns)", off)

    # ---- S07 duplicates / natural keys
    off, det = [], {}
    for t, keys in NATURAL_KEYS.items():
        for k in keys:
            bad = col(f"SELECT {k[0]} FROM {t} GROUP BY {', '.join(k)} HAVING COUNT(*) > 1")
            if bad: det[f"{t}({','.join(k)})"] = len(bad)
            off += [f"{t}({','.join(k)}):{b}" for b in bad]
    rep.add("S07", MP, "No duplicates on natural keys (dock number, plate, SCAC, shift, vehicle+request time, event type per appointment, ...)", off, det)

    # ---- S08 effective dates and simple ordering
    off = []
    for t in ["facilities", "docks", "yard_slots", "carriers", "vehicles"]:
        off += [f"{t}:{v}" for v in col(f"SELECT {PRIMARY_KEYS[t][0]} FROM {t} WHERE effective_to IS NOT NULL AND effective_to < effective_from")]
    off += [f"dock_calendar:{v}" for v in col("SELECT calendar_id FROM dock_calendar WHERE open_time >= close_time")]
    off += [f"labor_shifts:{v}" for v in col("SELECT shift_id FROM labor_shifts WHERE start_time >= end_time")]
    off += [f"facilities:{v}" for v in col("SELECT facility_id FROM facilities WHERE open_hour >= close_hour")]
    rep.add("S08", MP, "Date/time ordering on master data (effective_from <= effective_to, open < close, shift start < end)", off)

    # ---- S09 appointment time ordering
    off = col("SELECT appointment_id FROM appointments WHERE request_created_at >= requested_start")
    off += col("SELECT appointment_id FROM appointments WHERE scheduled_start IS NOT NULL AND scheduled_start < requested_start")
    off += col("SELECT appointment_id FROM appointments WHERE scheduled_start IS NOT NULL AND (scheduled_end <= scheduled_start OR substr(scheduled_start,1,10) != substr(scheduled_end,1,10))")
    off += col("SELECT appointment_id FROM appointments WHERE substr(requested_start,15,2) NOT IN ('00','30')")
    off += col(f"""SELECT a.appointment_id FROM appointments a JOIN checkin_events e ON e.appointment_id = a.appointment_id
                   WHERE e.event_type IN ('SCHEDULED','REJECTED') AND (e.event_time <= a.request_created_at OR e.event_time >= a.requested_start)""")
    rep.add("S09", MP, "Appointment timeline order: created < decision < requested <= scheduled start < end (same day); requests on the 30-min grid", off)

    # ---- S10 / S11 / S12 / S13 event timeline and lifecycle
    off = col("""SELECT event_id FROM (SELECT event_id, event_time, LAG(event_time) OVER (PARTITION BY appointment_id ORDER BY event_seq) p
                 FROM checkin_events) WHERE p IS NOT NULL AND event_time <= p""")
    rep.add("S10", MP, "Event timestamps strictly increase within each appointment", off)

    off = col("SELECT appointment_id FROM checkin_events GROUP BY appointment_id HAVING MIN(event_seq) != 1 OR MAX(event_seq) != COUNT(*)")
    off += col("SELECT appointment_id FROM appointments WHERE appointment_id NOT IN (SELECT appointment_id FROM checkin_events)")
    rep.add("S11", MP, "Every appointment has events, with sequence numbers 1..n and no gaps", off)

    conn.execute("CREATE TEMP TABLE legal (f TEXT, t TEXT)")
    conn.executemany("INSERT INTO legal VALUES (?,?)", sorted(LEGAL_TRANSITIONS))
    conn.execute("CREATE TEMP TABLE ev2s (e TEXT, s TEXT)")
    conn.executemany("INSERT INTO ev2s VALUES (?,?)", sorted(EVENT_TO_STATUS.items()))
    off = col("SELECT e.event_id FROM checkin_events e LEFT JOIN legal l ON l.f = e.from_status AND l.t = e.to_status WHERE l.f IS NULL")
    off += col("""SELECT event_id FROM (SELECT event_id, from_status, LAG(to_status) OVER (PARTITION BY appointment_id ORDER BY event_seq) p
                  FROM checkin_events) WHERE (p IS NULL AND from_status != 'REQUESTED') OR (p IS NOT NULL AND from_status != p)""")
    off += col("SELECT e.event_id FROM checkin_events e JOIN ev2s m ON m.e = e.event_type WHERE e.to_status != m.s")
    rep.add("S12", MP, "Lifecycle: every transition is legal, chains from the previous status, and matches its event type", off)

    off = col("""SELECT a.appointment_id FROM appointments a JOIN checkin_events e ON e.appointment_id = a.appointment_id
                 WHERE e.event_seq = (SELECT MAX(event_seq) FROM checkin_events WHERE appointment_id = a.appointment_id) AND a.status != e.to_status""")
    rep.add("S13", MP, "Appointment.status equals the to_status of its last event", off)

    # ---- R01 appointment totals reconcile with shipments
    off = col("""SELECT a.appointment_id FROM appointments a JOIN (SELECT appointment_id, SUM(pallets) p FROM shipments GROUP BY appointment_id) s
                 ON s.appointment_id = a.appointment_id WHERE a.total_pallets != s.p""")
    for aid, planned, m in Q("SELECT a.appointment_id, a.planned_duration_minutes, SUM(s.service_minutes) FROM appointments a JOIN shipments s ON s.appointment_id = a.appointment_id GROUP BY a.appointment_id"):
        if planned != math.ceil(m / SLOT_MINUTES) * SLOT_MINUTES: off.append(aid)
    off += col(f"SELECT appointment_id FROM appointments WHERE scheduled_start IS NOT NULL AND {mins('scheduled_start', 'scheduled_end')} != planned_duration_minutes")
    rep.add("R01", MP, "Appointment totals reconcile: pallets = sum of shipments; duration = sum of service minutes rounded up to 30; end - start = duration", off)

    # ---- R02 shipment service minutes = sum of its handling requirements
    off = []
    for sid, pallets, svc, total in Q("""SELECT s.shipment_id, s.pallets, s.service_minutes, SUM(h.fixed_minutes + h.minutes_per_pallet * s.pallets)
                                         FROM shipments s JOIN shipment_handling b ON b.shipment_id = s.shipment_id
                                         JOIN handling_requirements h ON h.handling_req_id = b.handling_req_id GROUP BY s.shipment_id"""):
        if svc != math.ceil(total): off.append(sid)
    rep.add("R02", MP, "Shipment service minutes = ceil(sum over its handling requirements of fixed + per-pallet x pallets)", off)

    off = col("""SELECT calendar_id FROM dock_calendar WHERE available_minutes !=
                 CASE WHEN status = 'OPEN' THEN (CAST(substr(close_time,1,2) AS INTEGER) - CAST(substr(open_time,1,2) AS INTEGER)) * 60 ELSE 0 END""")
    rep.add("R03", MP, "Calendar available_minutes = (close - open) x 60 when OPEN, else 0", off)

    # ---- R04 exceptions reconcile with the records they describe
    off = col(f"""SELECT x.exception_id FROM exceptions x JOIN appointments a ON a.appointment_id = x.appointment_id
                  WHERE x.exception_type = 'SLOT_SHIFTED' AND (a.scheduled_start IS NULL OR x.delay_minutes != {mins('a.requested_start', 'a.scheduled_start')} OR x.delay_minutes <= 0)""")
    off += col(f"""SELECT x.exception_id FROM exceptions x JOIN appointments a ON a.appointment_id = x.appointment_id
                   JOIN checkin_events e ON e.appointment_id = a.appointment_id AND e.event_type = 'CHECKED_IN'
                   WHERE x.exception_type = 'EARLY_ARRIVAL' AND (x.delay_minutes != {mins('e.event_time', 'a.scheduled_start')} OR x.delay_minutes < 30)""")
    off += col("SELECT x.exception_id FROM exceptions x JOIN appointments a ON a.appointment_id = x.appointment_id WHERE x.exception_type = 'NO_SHOW' AND a.status != 'NO_SHOW'")
    off += col("SELECT x.exception_id FROM exceptions x JOIN appointments a ON a.appointment_id = x.appointment_id WHERE x.exception_type = 'UNSCHEDULABLE' AND a.status != 'REJECTED'")
    off += col("SELECT exception_id FROM exceptions WHERE cause_code IS NULL OR cause_code = ''")
    rep.add("R04", MP, "Exceptions have cause codes and reconcile with their appointment (delay minutes, matching outcome)", off)

    # ---- R05 derived shipment status
    off = col("""SELECT s.shipment_id FROM shipments s JOIN appointments a ON a.appointment_id = s.appointment_id
                 WHERE s.status != CASE a.status WHEN 'COMPLETED' THEN 'COMPLETED' WHEN 'SCHEDULED' THEN 'PLANNED' WHEN 'REQUESTED' THEN 'PLANNED' ELSE 'NOT_HANDLED' END""")
    rep.add("R05", MP, "Shipment status is derived from its appointment's status", off)

    # ---- R06 field presence by status
    off = col("SELECT appointment_id FROM appointments WHERE status IN ('SCHEDULED','CHECKED_IN','AT_DOCK','SERVICED','COMPLETED','NO_SHOW') AND (dock_id IS NULL OR yard_slot_id IS NULL OR scheduled_start IS NULL)")
    off += col("SELECT appointment_id FROM appointments WHERE status = 'REJECTED' AND (dock_id IS NOT NULL OR scheduled_start IS NOT NULL)")
    rep.add("R06", MP, "Scheduled appointments have dock, yard slot and times; rejected ones have none", off)

    # ---- R07 shipment/handling cardinality
    off = col("SELECT appointment_id FROM appointments WHERE appointment_id NOT IN (SELECT appointment_id FROM shipments)")
    off += col("""SELECT s.shipment_id FROM shipments s LEFT JOIN (SELECT b.shipment_id, COUNT(*) n, MIN(h.load_type) lt FROM shipment_handling b
                  JOIN handling_requirements h ON h.handling_req_id = b.handling_req_id WHERE h.category = 'LOAD_CLASS' GROUP BY b.shipment_id) c
                  ON c.shipment_id = s.shipment_id WHERE c.n IS NULL OR c.n != 1 OR c.lt != s.load_type""")
    off += col("SELECT s.shipment_id FROM shipments s JOIN appointments a ON a.appointment_id = s.appointment_id WHERE s.load_type != a.load_type")
    rep.add("R07", MP, "Each appointment has >=1 shipment; each shipment has exactly one matching load-class requirement and its appointment's load type", off)

    # ---- R08 vehicle and yard consistency
    off = col("SELECT a.appointment_id FROM appointments a JOIN vehicles v ON v.vehicle_id = a.vehicle_id WHERE v.carrier_id != a.carrier_id OR a.total_pallets > v.capacity_pallets")
    off += col("""SELECT a.appointment_id FROM appointments a JOIN yard_slots y ON y.yard_slot_id = a.yard_slot_id
                  WHERE y.facility_id != a.facility_id OR y.slot_type != CASE a.load_type WHEN 'REFRIGERATED' THEN 'REEFER_PLUG' ELSE 'STANDARD' END""")
    off += col("SELECT a.appointment_id FROM appointments a JOIN docks d ON d.dock_id = a.dock_id WHERE d.facility_id != a.facility_id OR d.dock_mode NOT IN ('BOTH', a.direction)")
    rep.add("R08", MP, "Vehicle belongs to carrier and has capacity for the pallets; yard slot is in the facility and right type; dock is in the facility and allows the direction", off)

    # ---- R09 dock calendar: open that day and inside hours
    off = col("""SELECT a.appointment_id FROM appointments a LEFT JOIN dock_calendar c ON c.dock_id = a.dock_id AND c.calendar_date = substr(a.scheduled_start,1,10)
                 WHERE a.dock_id IS NOT NULL AND (c.calendar_id IS NULL OR c.status != 'OPEN' OR substr(a.scheduled_start,12,5) < c.open_time OR substr(a.scheduled_end,12,5) > c.close_time)""")
    rep.add("R09", MP, "Scheduled appointments fall on an OPEN dock-day and inside its opening hours", off)

    # ---- R10 crews (python sweep): usable crews never exceeded; every slot has a shift row at all
    cap, shift_win = {}, []
    for fac, d, s, e, crews, status, sid in Q("SELECT facility_id, shift_date, start_time, end_time, crews_available, status, shift_id FROM labor_shifts"):
        day = datetime.strptime(d, "%Y-%m-%d")
        t0, t1 = day + timedelta(hours=int(s[:2])), day + timedelta(hours=int(e[:2]))
        shift_win.append((fac, t0, t1, status, sid))
        if status == "SCHEDULED":
            t = t0
            while t < t1:
                cap[(fac, t)] = crews; t += timedelta(minutes=SLOT_MINUTES)
    covered = {(fac, t0 + timedelta(minutes=SLOT_MINUTES * i)) for fac, t0, t1, st, _ in shift_win
               for i in range(int((t1 - t0).total_seconds() // 60 // SLOT_MINUTES))}
    booked = Q("SELECT appointment_id, facility_id, scheduled_start, scheduled_end, vehicle_id, dock_id, status FROM appointments WHERE scheduled_start IS NOT NULL")
    used, uncovered = Counter(), []
    for aid, fac, s, e, *_ in booked:
        t, end = datetime.strptime(s, FMT), datetime.strptime(e, FMT)
        while t < end:
            used[(fac, t)] += 1
            if (fac, t) not in covered: uncovered.append(aid)
            t += timedelta(minutes=SLOT_MINUTES)
    rep.add("R10", MP, "Labor: every scheduled slot is covered by a shift row, and usable crews are never exceeded",
            [f"{k[0]}@{k[1].strftime(FMT)}" for k, n in used.items() if k in cap and n > cap[k]] + uncovered)

    # ---- R11 a vehicle cannot be in two places at once
    by_veh = defaultdict(list)
    for aid, fac, s, e, veh, *_ in booked:
        by_veh[veh].append((s, e, aid))
    off = []
    for lst in by_veh.values():
        lst.sort()
        off += [f"{x[2]}/{y[2]}" for x, y in zip(lst, lst[1:]) if y[0] < max(x[1], y[0]) and y[0] < x[1]]
    rep.add("R11", MP, "No vehicle is booked at two docks at overlapping times", off)

    # ================= detectors: the five business rules =================
    # B01 dock overlap (scheduled intervals)
    by_dock = defaultdict(list)
    for aid, fac, s, e, veh, dock, status in booked:
        by_dock[dock].append((s, e, aid))
    pairs = []
    for lst in by_dock.values():
        lst.sort()
        for i, (s, e, x) in enumerate(lst):
            for s2, e2, y in lst[i + 1:]:
                if s2 >= e: break
                pairs.append([x, y])
    rep.add("B01", "detector", "DOCK_OVERLAP: two appointments overlap on the same dock (capacity 1)", [f"{x}/{y}" for x, y in pairs])
    rep.findings["DOCK_OVERLAP"] = {"pairs": pairs}

    # B02 incompatible load (dock type or vehicle capability)
    dock_type = dict(Q("SELECT dock_id, dock_type FROM docks"))
    veh = {r[0]: r for r in Q("SELECT vehicle_id, is_refrigerated, hazmat_certified FROM vehicles")}
    bad = set()
    for aid, load, dock, vid in Q("SELECT appointment_id, load_type, dock_id, vehicle_id FROM appointments WHERE dock_id IS NOT NULL"):
        if dock_type[dock] not in COMPATIBLE_DOCKS[load]: bad.add(aid)
        if (load == "REFRIGERATED" and not veh[vid][1]) or (load == "HAZARDOUS" and not veh[vid][2]): bad.add(aid)
    rep.add("B02", "detector", "INCOMPATIBLE_LOAD: dock type or vehicle cannot handle the load (refrigerated/hazardous)", bad)
    rep.findings["INCOMPATIBLE_LOAD"] = {"records": sorted(bad)}

    # B03 check-in before the appointment date
    bad = col("""SELECT e.event_id FROM checkin_events e JOIN appointments a ON a.appointment_id = e.appointment_id
                 WHERE e.event_type = 'CHECKED_IN' AND substr(e.event_time,1,10) < substr(a.scheduled_start,1,10)""")
    rep.add("B03", "detector", "CHECKIN_BEFORE_DATE: CHECKED_IN event is dated before the appointment date", bad)
    rep.findings["CHECKIN_BEFORE_DATE"] = {"records": sorted(bad)}

    # B04 labor shift not available (appointment overlaps a CANCELLED shift)
    bad_appts, bad_shifts = set(), set()
    for fac, t0, t1, status, sid in shift_win:
        if status != "CANCELLED": continue
        for aid, f2, s, e, *_ in booked:
            if f2 == fac and datetime.strptime(s, FMT) < t1 and datetime.strptime(e, FMT) > t0:
                bad_appts.add(aid); bad_shifts.add(sid)
    rep.add("B04", "detector", "LABOR_SHIFT_UNAVAILABLE: appointment overlaps a CANCELLED labor shift", bad_appts)
    rep.findings["LABOR_SHIFT_UNAVAILABLE"] = {"records": sorted(bad_appts), "shifts": sorted(bad_shifts)}

    # B05 no-show not recorded: slot ended, still SCHEDULED, no check-in and no no-show event
    cutoff = Q("SELECT MAX(calendar_date) FROM dock_calendar")[0][0] + "T23:59"          # data cut-off derived from the data
    bad = col(f"""SELECT a.appointment_id FROM appointments a WHERE a.status = 'SCHEDULED' AND a.scheduled_end < '{cutoff}'
                  AND NOT EXISTS (SELECT 1 FROM checkin_events e WHERE e.appointment_id = a.appointment_id AND e.event_type IN ('CHECKED_IN','NO_SHOW'))""")
    rep.add("B05", "detector", "NO_SHOW_NOT_RECORDED: slot has ended, appointment still SCHEDULED, no check-in or no-show event", bad)
    rep.findings["NO_SHOW_NOT_RECORDED"] = {"records": sorted(bad)}

    # I01 physical overlap from ACTUAL events (information only; supports DOCK_OVERLAP)
    runs = defaultdict(list)
    for aid, dock, s, e in Q("""SELECT a.appointment_id, a.dock_id, s.event_time, e.event_time FROM appointments a
                                JOIN checkin_events s ON s.appointment_id = a.appointment_id AND s.event_type = 'DOCK_STARTED'
                                JOIN checkin_events e ON e.appointment_id = a.appointment_id AND e.event_type = 'DOCK_COMPLETED'"""):
        runs[dock].append((s, e, aid))
    phys = []
    for lst in runs.values():
        lst.sort()
        phys += [f"{x[2]}/{y[2]}" for x, y in zip(lst, lst[1:]) if y[0] < x[1]]
    rep.add("I01", "detector", "Information: trucks physically on the same dock at the same time (from actual events)", phys)
    return rep


def main():
    p = argparse.ArgumentParser(description="Validate an exported dataset")
    p.add_argument("--scale", default="starter")
    p.add_argument("--out", default="output")
    a = p.parse_args()
    data_dir = os.path.join(a.out, a.scale)
    conn, optional = load_db(data_dir)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    rep = run(conn, optional)

    must = [r for r in rep.results if r["kind"] == "must_pass"]
    failed = [r for r in must if r["violations"]]
    out_dir = os.path.join(data_dir, "validation")
    os.makedirs(out_dir, exist_ok=True)
    summary = {"dataset": data_dir, "row_counts": counts, "must_pass_checks": len(must), "must_pass_failed": len(failed),
               "detector_findings": {r["id"]: r["violations"] for r in rep.results if r["kind"] == "detector"},
               "checks": rep.results}
    with open(os.path.join(out_dir, "validation_summary.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2); fh.write("\n")
    with open(os.path.join(out_dir, "findings.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rep.findings, fh, indent=1, sort_keys=True); fh.write("\n")

    print(f"Validated {data_dir}: {sum(counts.values()):,} rows in {len(counts)} tables\n")
    for r in rep.results:
        tag = ("PASS" if not r["violations"] else "FAIL") if r["kind"] == "must_pass" else f"{r['violations']:>4}"
        print(f"  [{tag:>4}] {r['id']}  {r['description']}" + (f"   e.g. {r['sample'][:2]}" if r["violations"] else ""))
    print(f"\nMust-pass checks: {len(must) - len(failed)}/{len(must)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()