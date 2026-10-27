"""anomalies.py - Step 5: AFTER the clean baseline exists, deliberately break specific rows
and record every change in the ground truth.

Principles
  * each change touches ONE field of ONE record (so the cause is exact);
  * a record is broken at most once (the `used` set), so labels never overlap;
  * derived values are recomputed from the changed source, never left half-updated;
  * everything else stays byte-identical to the baseline.
"""
from collections import defaultdict
from datetime import datetime, timedelta

import ids
from config import ANOMALY_RATE, MIN_PER_TYPE, MAX_APPTS_PER_CANCELLED_SHIFT, COMPATIBLE_DOCKS
from demand import FMT
from models import GroundTruth

RULES = {
    "DOCK_OVERLAP": "Two appointments on the same dock have overlapping scheduled intervals (dock capacity is 1).",
    "INCOMPATIBLE_LOAD": "Load type needs a dock type or vehicle capability that the assigned dock/vehicle lacks.",
    "CHECKIN_BEFORE_DATE": "CHECKED_IN event date is earlier than the appointment's scheduled date.",
    "LABOR_SHIFT_UNAVAILABLE": "Appointment overlaps a labor shift whose status is CANCELLED (no crew available).",
    "NO_SHOW_NOT_RECORDED": "Appointment is still SCHEDULED after its slot ended, with no CHECKED_IN or NO_SHOW event.",
}


def inject_anomalies(appts, shipments, events, excs, docks, vehicles, shifts, dock_cal, scale, rng):
    n_target = max(MIN_PER_TYPE, round(scale.appointments * ANOMALY_RATE))
    gt, used = [], set()

    def add(issue_type, table, record, related, field, old, new):
        gt.append(GroundTruth(ids.ground_truth_id(len(gt) + 1), issue_type, table, record,
                              related, field, None if old is None else str(old),
                              None if new is None else str(new), RULES[issue_type]))

    # ---- lookup structures built once from the CLEAN baseline ----
    dock_by = {d.dock_id: d for d in docks}
    closed = {(c.dock_id, c.calendar_date) for c in dock_cal if c.status != "OPEN"}
    booked = [a for a in appts if a.status in ("COMPLETED", "NO_SHOW")]
    worked = [a for a in booked if a.status == "COMPLETED"]
    st = {a.appointment_id: datetime.strptime(a.scheduled_start, FMT) for a in booked}
    en = {a.appointment_id: st[a.appointment_id] + timedelta(minutes=a.planned_duration_minutes) for a in booked}
    by_fac_day, by_dock_day = defaultdict(list), defaultdict(list)
    for a in booked:
        by_fac_day[(a.facility_id, a.scheduled_start[:10])].append(a)
        by_dock_day[(a.dock_id, a.scheduled_start[:10])].append(a)
    ev_by = defaultdict(dict)
    for e in events.rows:
        ev_by[e.appointment_id][e.event_type] = e
    ships_by = defaultdict(list)
    for s in shipments:
        ships_by[s.appointment_id].append(s)
    early_exc = {e.appointment_id for e in excs.rows if e.exception_type == "EARLY_ARRIVAL"}
    veh_by_carrier = defaultdict(list)
    for v in vehicles:
        veh_by_carrier[v.carrier_id].append(v)

    def overlaps(a_id, s, e):
        return st[a_id] < e and en[a_id] > s

    def move(x, new_dock):                      # keep the dock index in step with the change
        day = x.scheduled_start[:10]
        by_dock_day[(x.dock_id, day)].remove(x)
        by_dock_day[(new_dock, day)].append(x)
        x.dock_id = new_dock

    def shuffled(items):
        items = list(items)
        rng.shuffle(items)
        return items

    # ---- 1. DOCK_OVERLAP: move X onto a compatible dock where exactly one other truck already is ----
    made = 0
    for x in shuffled(worked):
        if made >= n_target:
            break
        if x.appointment_id in used:
            continue
        xs, xe, day = st[x.appointment_id], en[x.appointment_id], x.scheduled_start[:10]
        ys = []
        for y in by_fac_day[(x.facility_id, day)]:
            if y.status != "COMPLETED" or y.appointment_id in used or y.dock_id == x.dock_id:
                continue
            if min(xe, en[y.appointment_id]) - max(xs, st[y.appointment_id]) < timedelta(minutes=30):
                continue
            dk = dock_by[y.dock_id]
            if dk.dock_type not in COMPATIBLE_DOCKS[x.load_type] or dk.dock_mode not in ("BOTH", x.direction):
                continue                                           # keep the ONLY violation = overlap
            if any(z is not y and overlaps(z.appointment_id, xs, xe) for z in by_dock_day[(y.dock_id, day)]):
                continue
            ys.append(y)
        if not ys:
            continue
        y = rng.choice(ys)
        old = x.dock_id
        move(x, y.dock_id)
        used |= {x.appointment_id, y.appointment_id}
        add("DOCK_OVERLAP", "appointments", x.appointment_id, y.appointment_id, "dock_id", old, y.dock_id)
        made += 1

    # ---- 2. INCOMPATIBLE_LOAD: reefer/hazmat load on a standard dock (60%) or a wrong vehicle (40%) ----
    made = 0
    for x in shuffled(a for a in worked if a.load_type != "AMBIENT"):
        if made >= n_target:
            break
        if x.appointment_id in used:
            continue
        day = x.scheduled_start[:10]
        lo, hi = st[x.appointment_id] - timedelta(minutes=60), en[x.appointment_id] + timedelta(minutes=60)
        done = False
        if rng.random() < 0.6:
            free = [d for d in docks if d.facility_id == x.facility_id and d.dock_type == "STANDARD"
                    and d.dock_mode in ("BOTH", x.direction) and (d.dock_id, day) not in closed
                    and not any(overlaps(z.appointment_id, lo, hi) for z in by_dock_day[(d.dock_id, day)])]
            if free:
                d = rng.choice(free)
                old = x.dock_id
                move(x, d.dock_id)
                add("INCOMPATIBLE_LOAD", "appointments", x.appointment_id, None, "dock_id", old, d.dock_id)
                done = True
        if not done:
            ok_attr = (lambda v: v.is_refrigerated) if x.load_type == "REFRIGERATED" else (lambda v: v.hazmat_certified)
            #Select an incompatible vehicle without introducing double-booking
            bad = [v for v in veh_by_carrier[x.carrier_id]
                   if not ok_attr(v) 
                   and v.capacity_pallets >= x.total_pallets
                   and not any(
                       other.appointment_id != x.appointment_id
                       and other.vehicle_id == v.vehicle_id
                       and overlaps(
                           other.appointment_id, 
                           st[x.appointment_id], 
                           en[x.appointment_id]
                           )
                       for other in booked
                   )
                   ]
            if not bad:
                continue
            v = rng.choice(bad)
            old, x.vehicle_id = x.vehicle_id, v.vehicle_id
            add("INCOMPATIBLE_LOAD", "appointments", x.appointment_id, None, "vehicle_id", old, v.vehicle_id)
        used.add(x.appointment_id)
        made += 1

    # ---- 3. CHECKIN_BEFORE_DATE: move one CHECKED_IN event to the evening before the slot ----
    made = 0
    for x in shuffled(worked):
        if made >= n_target:
            break
        if x.appointment_id in used or x.appointment_id in early_exc:
            continue
        day0 = datetime(st[x.appointment_id].year, st[x.appointment_id].month, st[x.appointment_id].day)
        new = (day0 - timedelta(minutes=rng.randint(30, 600))).strftime(FMT)     # 14:00-23:30 the day before
        chk, sched = ev_by[x.appointment_id]["CHECKED_IN"], ev_by[x.appointment_id]["SCHEDULED"]
        if new <= sched.event_time:
            continue                                  # would break event ORDER too; pick another record
        old, chk.event_time = chk.event_time, new
        used.add(x.appointment_id)
        add("CHECKIN_BEFORE_DATE", "checkin_events", chk.event_id, x.appointment_id, "event_time", old, new)
        made += 1

    # ---- 4. LABOR_SHIFT_UNAVAILABLE: cancel a small shift that already has appointments in it ----
    cands = []
    for sh in shifts:
        if sh.status != "SCHEDULED":
            continue
        w0 = datetime.strptime(f"{sh.shift_date} {sh.start_time}", "%Y-%m-%d %H:%M")
        w1 = datetime.strptime(f"{sh.shift_date} {sh.end_time}", "%Y-%m-%d %H:%M")
        hit = [a for a in by_fac_day[(sh.facility_id, sh.shift_date)] if overlaps(a.appointment_id, w0, w1)]
        if 1 <= len(hit) <= MAX_APPTS_PER_CANCELLED_SHIFT and not any(a.appointment_id in used for a in hit):
            cands.append((sh, hit))
    total = 0
    for sh, hit in shuffled(cands):
        if total >= n_target:
            break
        if any(a.appointment_id in used for a in hit):
            continue
        sh.status = "CANCELLED"
        add("LABOR_SHIFT_UNAVAILABLE", "labor_shifts", sh.shift_id, None, "status", "SCHEDULED", "CANCELLED")
        for a in hit:
            used.add(a.appointment_id)
            add("LABOR_SHIFT_UNAVAILABLE", "appointments", a.appointment_id, sh.shift_id, "scheduled_start", None, None)
        total += len(hit)

    # ---- 5. NO_SHOW_NOT_RECORDED: the no-show happened but its event/exception was never written ----
    made = 0
    ex_by = {e.appointment_id: e for e in excs.rows if e.exception_type == "NO_SHOW"}
    for x in shuffled(a for a in appts if a.status == "NO_SHOW"):
        if made >= n_target:
            break
        if x.appointment_id in used:
            continue
        ev = ev_by[x.appointment_id]["NO_SHOW"]
        events.rows.remove(ev)
        excs.rows.remove(ex_by[x.appointment_id])
        x.status = "SCHEDULED"                        # stale state: nothing ever moved it on
        for s in ships_by[x.appointment_id]:
            s.status = "PLANNED"                      # derived from the (now stale) appointment status
        used.add(x.appointment_id)
        add("NO_SHOW_NOT_RECORDED", "appointments", x.appointment_id, ev.event_id, "status", "NO_SHOW", "SCHEDULED")
        made += 1

    events.rows.sort(key=lambda e: (e.event_time, e.appointment_id, e.event_seq))   # keep log in time order
    return gt