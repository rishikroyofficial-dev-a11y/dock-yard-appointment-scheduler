"""main.py - command-line entry point.

Usage:  python main.py --scale starter
        python main.py --scale full --seed 20261022 --out output
"""
import argparse
import dataclasses
import json
import os
import random
from collections import Counter
 
import allocator
import anomalies
import calendars
import demand
import master_data as md
import metrics
import simulator
from config import SEED, SCALES
from events import EventLog, ExceptionLog
from export import write_csv, sha256_of
from models import (Facility, Dock, YardSlot, Carrier, Vehicle, LaborShift, DockCalendar,
                    HandlingRequirement, Appointment, Shipment, ShipmentHandling,
                    CheckInEvent, ExceptionRecord, GroundTruth)
 
 
def build_all(scale, seed, inject=True):
    # One independent random stream per stage: changing one stage never shifts another.
    R = lambda name: random.Random(f"{seed}:{name}")
 
    facilities = md.generate_facilities(scale)
    docks = md.generate_docks(facilities, scale, R("docks"))
    yard = md.generate_yard_slots(facilities, scale)
    carriers = md.generate_carriers(scale)
    vehicles = md.generate_vehicles(carriers, R("vehicles"))
 
    shifts = calendars.generate_labor_shifts(facilities, scale, R("labor"))
    dock_cal = calendars.generate_dock_calendars(facilities, docks, scale, R("dockcal"))
 
    hreqs = demand.generate_handling_requirements()
    appts, ships, bridge, peak_dates = demand.generate_demand(
        facilities, carriers, vehicles, hreqs, scale, R("demand"))
 
    # Scheduling then simulation; both ADD to the append-only logs and fill current state in place.
    events, excs = allocator.run_allocation(
        appts, facilities, docks, yard, dock_cal, shifts, scale, R("alloc"))
    simulator.run_simulation(appts, ships, carriers, events, excs, R("sim"))
 
    ground_truth = []
    if inject:       # only AFTER the clean baseline exists: deliberately break labelled rows
        ground_truth = anomalies.inject_anomalies(appts, ships, events, excs, docks, vehicles,
                                                  shifts, dock_cal, scale, R("anomaly"))
 
    tables = {"facilities": (facilities, Facility), "docks": (docks, Dock),
              "yard_slots": (yard, YardSlot), "carriers": (carriers, Carrier),
              "vehicles": (vehicles, Vehicle), "labor_shifts": (shifts, LaborShift),
              "dock_calendar": (dock_cal, DockCalendar),
              "handling_requirements": (hreqs, HandlingRequirement),
              "appointments": (appts, Appointment), "shipments": (ships, Shipment),
              "shipment_handling": (bridge, ShipmentHandling),
              "checkin_events": (events.rows, CheckInEvent), "exceptions": (excs.rows, ExceptionRecord)}
    return tables, peak_dates, ground_truth
 
 
def main():
    p = argparse.ArgumentParser(description="YottaFlex dock-appointment data generator")
    p.add_argument("--scale", choices=SCALES.keys(), default="starter")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="output")
    p.add_argument("--no-anomalies", action="store_true", help="export the clean baseline only")
    args = p.parse_args()
 
    tables, peak_dates, ground_truth = build_all(SCALES[args.scale], args.seed, inject=not args.no_anomalies)
    out_dir = os.path.join(args.out, args.scale)
    for name, (rows, row_type) in tables.items():
        path = os.path.join(out_dir, f"{name}.csv")
        write_csv(path, rows, row_type)
        print(f"{name:22} {len(rows):7} rows  sha256={sha256_of(path)[:12]}")
 
    if ground_truth:                                   # separate folder: never mixed into the data tables
        gt_dir = os.path.join(out_dir, "ground_truth")
        write_csv(os.path.join(gt_dir, "ground_truth.csv"), ground_truth, GroundTruth)
        with open(os.path.join(gt_dir, "ground_truth.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump([dataclasses.asdict(g) for g in ground_truth], fh, indent=2)
            fh.write("\n")
        counts = Counter(g.issue_type for g in ground_truth if g.table_name != "labor_shifts")
        print(f"{'ground_truth':22} {len(ground_truth):7} rows  (anomalous records by type: {dict(sorted(counts.items()))})")
 
    # Measurable outputs, computed from the records only.
    k = metrics.compute_kpis(tables["appointments"][0], tables["checkin_events"][0], tables["docks"][0],
                             tables["dock_calendar"][0], tables["exceptions"][0], peak_dates)
    kpi_path = os.path.join(out_dir, "kpi_summary.json")
    with open(kpi_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(k, fh, indent=2, sort_keys=True)
        fh.write("\n")
    w, wp, wo = k["wait_minutes_checkin_to_dock"], k["wait_minutes_peak_days"], k["wait_minutes_other_days"]
    print(f"\nPeak days: {', '.join(peak_dates)}")
    print(f"Status: {k['appointments_by_status']}")
    print(f"Events: {k['events_total']:,} | no-show rate {k['no_show_rate']:.1%} | early arrivals {k['early_arrival_rate']:.1%}"
          f" | on-time dock start {k['on_time_dock_start_rate_15min']:.1%}")
    print(f"Wait check-in->dock (min): mean {w['mean']}, median {w['median']}, p95 {w['p95']} | "
          f"peak days mean {wp['mean']} vs other days {wo['mean']}")
    print(f"Actual dock utilisation: {k['actual_dock_utilisation']}")
    print(f"Exceptions by type: {k['exceptions_by_type']}")
    print(f"Exceptions by cause: {k['exceptions_by_cause']}")
    print(f"kpi_summary.json sha256={sha256_of(kpi_path)[:12]}")
 
 
if __name__ == "__main__":
    main()


#main: runner file
"""
main.py: the command-line entry point. 
--scale picks starter or full, and --seed and --out are optional.

"""