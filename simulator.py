"""simulator.py - plays out the day for every scheduled appointment.

Each dock is processed in time order, remembering when its previous truck finished
(dock_free). That one rule is what creates congestion: a late or slow truck pushes
the next truck on the same dock back. Nothing is labelled "congested" at random.

Per appointment:  no-show?  ->  arrival offset  ->  check-in  ->  dock start
                  (>= slot, >= check-in + gate move, >= dock_free)  ->  service  ->  departure
"""
from collections import defaultdict
from datetime import datetime, timedelta

from config import (NO_SHOW_RATE_RANGE, NO_SHOW_GRACE_MINUTES, EARLY_BIRD_PROB, EARLY_BIRD_MINUTES,
                    ARRIVAL_MEAN, ARRIVAL_SD, ARRIVAL_CLIP, EARLY_ARRIVAL_THRESHOLD,
                    GATE_TO_DOCK_MINUTES, GATE_OUT_MINUTES, SERVICE_FACTOR, CONGESTION_THRESHOLD)
from demand import FMT


def _f(dt):
    return dt.strftime(FMT)


def _congestion_severity(m):
    return "LOW" if m < 60 else "MEDIUM" if m < 120 else "HIGH"


def run_simulation(appts, shipments, carriers, events, excs, rng):
    # Each carrier has its own reliability (drawn once, in a fixed order).
    no_show_rate = {c.carrier_id: rng.uniform(*NO_SHOW_RATE_RANGE)
                    for c in sorted(carriers, key=lambda c: c.carrier_id)}
    planned_service = defaultdict(int)
    for s in shipments:
        planned_service[s.appointment_id] += s.service_minutes

    todo = sorted((a for a in appts if a.status == "SCHEDULED"),
                  key=lambda a: (a.dock_id, a.scheduled_start, a.appointment_id))
    dock_free = {}                                   # dock_id -> when its last truck finished
    for a in todo:
        slot = datetime.strptime(a.scheduled_start, FMT)

        if rng.random() < no_show_rate[a.carrier_id]:                    # ---- no-show path
            t = _f(slot + timedelta(minutes=NO_SHOW_GRACE_MINUTES))
            events.append(a.appointment_id, "NO_SHOW", "SCHEDULED", "NO_SHOW", t, "GATE")
            excs.append(a.appointment_id, "NO_SHOW", "NO_SHOW", "MEDIUM", t, None,
                        f"Truck did not arrive within {NO_SHOW_GRACE_MINUTES} min of the slot")
            a.status = "NO_SHOW"
            continue

        if rng.random() < EARLY_BIRD_PROB:                               # ---- arrival
            offset = -rng.randint(*EARLY_BIRD_MINUTES)
        else:
            offset = max(ARRIVAL_CLIP[0], min(ARRIVAL_CLIP[1], round(rng.gauss(ARRIVAL_MEAN, ARRIVAL_SD))))
        check_in = slot + timedelta(minutes=offset)
        ready = max(check_in + timedelta(minutes=rng.randint(*GATE_TO_DOCK_MINUTES)), slot)
        start = max(ready, dock_free.get(a.dock_id, ready))              # wait if dock still occupied
        service = max(1, round(planned_service[a.appointment_id] * rng.triangular(*SERVICE_FACTOR)))
        done = start + timedelta(minutes=service)
        depart = done + timedelta(minutes=rng.randint(*GATE_OUT_MINUTES))
        dock_free[a.dock_id] = done

        i = a.appointment_id
        events.append(i, "CHECKED_IN", "SCHEDULED", "CHECKED_IN", _f(check_in), "GATE")
        events.append(i, "DOCK_STARTED", "CHECKED_IN", "AT_DOCK", _f(start), "DOCK_OPS")
        events.append(i, "DOCK_COMPLETED", "AT_DOCK", "SERVICED", _f(done), "DOCK_OPS")
        events.append(i, "DEPARTED", "SERVICED", "COMPLETED", _f(depart), "GATE")
        a.status = "COMPLETED"

        if -offset >= EARLY_ARRIVAL_THRESHOLD:                           # ---- exceptions from rules
            excs.append(i, "EARLY_ARRIVAL", "EARLY_ARRIVAL", "LOW" if -offset < 90 else "MEDIUM",
                        _f(check_in), -offset, f"Arrived {-offset} min before the slot")
        blocked = int((start - ready).total_seconds() // 60)
        if blocked >= CONGESTION_THRESHOLD:
            excs.append(i, "CONGESTION_DELAY", "DOCK_STILL_OCCUPIED", _congestion_severity(blocked),
                        _f(ready), blocked, f"Truck ready at {_f(ready)} but dock busy until {_f(done - timedelta(minutes=service))}")

    # Shipment outcome is DERIVED from its appointment's final status.
    final = {a.appointment_id: a.status for a in appts}
    for s in shipments:
        s.status = "COMPLETED" if final[s.appointment_id] == "COMPLETED" else "NOT_HANDLED"
    # Present the append-only log in time order (IDs and content are unchanged).
    events.rows.sort(key=lambda e: (e.event_time, e.appointment_id, e.event_seq))