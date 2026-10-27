"""allocator.py - the scheduling logic (first-come-first-served, earliest feasible slot).

For each request, in booking order, find the earliest start >= the requested start where:
  1. a COMPATIBLE dock is free (load type, direction mode, no overlap, open per calendar)
  2. a labor crew is free for the whole duration (cancelled shifts give zero crews)
  3. a suitable yard slot is free for the hour before the dock start
Among free docks, pick the least-booked one (spreads load). If nothing fits within
MAX_SHIFT_DAYS, the request is REJECTED. Every decision is logged as an event/exception.

Time is a grid of 30-minute slots: index = day_index * 48 + slot_of_day.
"""
from collections import defaultdict, Counter
from datetime import datetime, timedelta

from calendars import day_list, hours_for
from config import (START_DATE, SLOT_MINUTES, COMPATIBLE_DOCKS, MAX_SHIFT_DAYS,
                    OVERFLOW_AFTER_MINUTES, YARD_BUFFER_SLOTS)
from demand import FMT
from events import EventLog, ExceptionLog

SPH = 60 // SLOT_MINUTES          # slots per hour (2)
SPD = 24 * SPH                    # slots per day (48)
# Preferred dock type per load; special docks are protected for the loads that NEED them.
PRIMARY_DOCK = {"AMBIENT": ["STANDARD"], "REFRIGERATED": ["REEFER"], "HAZARDOUS": ["HAZMAT_CERTIFIED"]}


class Allocator:
    def __init__(self, facilities, docks, yard_slots, dock_cal, shifts, scale):
        self.n_days = scale.days
        self.days = day_list(scale)
        day_index = {d.isoformat(): i for i, d in enumerate(self.days)}
        self.fac_by_id = {f.facility_id: f for f in facilities}

        self.docks_by_fac = defaultdict(list)
        for d in sorted(docks, key=lambda d: (d.facility_id, d.dock_number)):
            self.docks_by_fac[d.facility_id].append(d)
        self.occ = {d.dock_id: bytearray(self.n_days * SPD) for d in docks}   # 1 = slot taken
        self.booked = {d.dock_id: 0 for d in docks}                            # minutes booked so far

        self.cal = {}                                  # (dock_id, day) -> (is_open, open_slot, close_slot)
        for c in dock_cal:
            self.cal[(c.dock_id, day_index[c.calendar_date])] = (
                c.status == "OPEN", int(c.open_time[:2]) * SPH, int(c.close_time[:2]) * SPH)

        n = self.n_days * SPD                          # labor: crews available / used per slot
        self.crew_cap = {f.facility_id: [0] * n for f in facilities}
        self.crew_used = {f.facility_id: [0] * n for f in facilities}
        for sh in shifts:
            if sh.status != "SCHEDULED":
                continue                               # cancelled shift = zero crews
            base = day_index[sh.shift_date] * SPD
            for slot in range(int(sh.start_time[:2]) * SPH, int(sh.end_time[:2]) * SPH):
                self.crew_cap[sh.facility_id][base + slot] = sh.crews_available

        self.yard_by = defaultdict(list)
        for y in sorted(yard_slots, key=lambda y: (y.facility_id, y.slot_number)):
            self.yard_by[(y.facility_id, y.slot_type)].append(y.yard_slot_id)
        self.yard_occ = {y.yard_slot_id: bytearray(n) for y in yard_slots}
        self._cand_cache = {}
        self.vehicle_occ = {} #vehicle's occupancy arr whn that vehc is first encountered

    # ---- individual rule checks ----
    def _candidates(self, fac, load, direction, flex):
        key = (fac, load, direction, flex)
        if key not in self._cand_cache:
            types = COMPATIBLE_DOCKS[load] if flex else PRIMARY_DOCK[load]
            self._cand_cache[key] = [d for d in self.docks_by_fac[fac]
                                     if d.dock_type in types and d.dock_mode in ("BOTH", direction)]
        return self._cand_cache[key]

    def _dock_open(self, dock_id, di, s, k):
        is_open, o, c = self.cal[(dock_id, di)]
        return is_open and s >= o and s + k <= c

    def _dock_free(self, dock_id, di, s, k):
        base = di * SPD + s
        return self._dock_open(dock_id, di, s, k) and 1 not in self.occ[dock_id][base:base + k]

    def _crew_ok(self, fac, di, s, k):
        cap, used = self.crew_cap[fac], self.crew_used[fac]
        base = di * SPD + s
        return all(cap[i] - used[i] >= 1 for i in range(base, base + k))

    def _yard_slot(self, fac, load, di, s):
        stype = "REEFER_PLUG" if load == "REFRIGERATED" else "STANDARD"
        base = di * SPD + s
        for ys in self.yard_by[(fac, stype)]:
            if 1 not in self.yard_occ[ys][base - YARD_BUFFER_SLOTS:base]:
                return ys
        return None

    # ---- why did the REQUESTED slot fail? (gives every shift a cause code) ----
    def diagnose(self, a, di, s, k):
        docks = self._candidates(a.facility_id, a.load_type, a.direction, False)
        open_docks = [d for d in docks if self._dock_open(d.dock_id, di, s, k)]
        if not open_docks:
            maint = any(not self.cal[(d.dock_id, di)][0] for d in docks)
            return "DOCK_MAINTENANCE" if maint else "OUTSIDE_OPERATING_HOURS"
        if not any(self._dock_free(d.dock_id, di, s, k) for d in open_docks):
            return "DOCK_CAPACITY_FULL"
        if not self._crew_ok(a.facility_id, di, s, k):
            return "LABOR_SHORTAGE"
        return "YARD_FULL"

    # ---- the search ----
    def allocate(self, a):
        req = datetime.strptime(a.requested_start, FMT)
        d0 = (req.date() - START_DATE).days
        s0 = req.hour * SPH + req.minute // SLOT_MINUTES
        k = a.planned_duration_minutes // SLOT_MINUTES
        if a.vehicle_id not in self.vehicle_occ:
            self.vehicle_occ[a.vehicle_id] = bytearray(
                self.n_days * SPD
            )
        fac = self.fac_by_id[a.facility_id]
        for off in range(MAX_SHIFT_DAYS + 1):
            di = d0 + off
            if di >= self.n_days:
                break                                   # never schedule past the 60-day window
            open_h, close_h = hours_for(fac, self.days[di])
            first = s0 if off == 0 else open_h * SPH
            for s in range(first, close_h * SPH - k + 1):
                wait = ((di - d0) * SPD + s - s0) * SLOT_MINUTES
                base = di * SPD + s

                #a vehicle can't serve 2 appntments simulataneously
                if 1 in self.vehicle_occ[a.vehicle_id][base: base + k]:
                    continue
                if not self._crew_ok(a.facility_id, di, s, k):
                    continue
                flex = wait >= OVERFLOW_AFTER_MINUTES
                free = [d for d in self._candidates(a.facility_id, a.load_type, a.direction, flex)
                        if self._dock_free(d.dock_id, di, s, k)]
                if not free:
                    continue
                yard = self._yard_slot(a.facility_id, a.load_type, di, s)
                if yard is None:
                    continue
                dock = min(free, key=lambda d: (self.booked[d.dock_id], d.dock_number))
                cause = self.diagnose(a, d0, s0, k) if wait > 0 else None   # BEFORE booking
                base = di * SPD + s
                self.occ[dock.dock_id][base:base + k] = b"\x01" * k
                self.vehicle_occ[a.vehicle_id][base: base + k] = b"\x01" * k
                for i in range(base, base + k):
                    self.crew_used[a.facility_id][i] += 1
                self.yard_occ[yard][base - YARD_BUFFER_SLOTS:base] = b"\x01" * YARD_BUFFER_SLOTS
                self.booked[dock.dock_id] += k * SLOT_MINUTES
                return dock.dock_id, yard, di, s, wait, cause
        return None


def _severity(delay):
    return "LOW" if delay < 120 else "MEDIUM" if delay < 1440 else "HIGH"


def run_allocation(appts, facilities, docks, yard_slots, dock_cal, shifts, scale, rng):
    """Schedules every appointment IN PLACE (current state) and returns the history logs."""
    alloc = Allocator(facilities, docks, yard_slots, dock_cal, shifts, scale)
    events, excs = EventLog(), ExceptionLog()
    for a in sorted(appts, key=lambda a: (a.request_created_at, a.appointment_id)):   # booking order
        created = datetime.strptime(a.request_created_at, FMT)
        decided = (created + timedelta(minutes=rng.randint(15, 180))).strftime(FMT)
        res = alloc.allocate(a)
        if res is None:
            a.status = "REJECTED"
            events.append(a.appointment_id, "REJECTED", "REQUESTED", "REJECTED", decided, "ALLOCATOR")
            excs.append(a.appointment_id, "UNSCHEDULABLE", "NO_WINDOW_IN_HORIZON", "HIGH", decided, None,
                        f"No feasible slot within {MAX_SHIFT_DAYS} days of {a.requested_start} or before the end of the window")
            continue
        dock_id, yard_id, di, s, wait, cause = res
        start = datetime.combine(alloc.days[di], datetime.min.time()) + timedelta(minutes=s * SLOT_MINUTES)
        a.dock_id, a.yard_slot_id = dock_id, yard_id
        a.scheduled_start = start.strftime(FMT)
        a.scheduled_end = (start + timedelta(minutes=a.planned_duration_minutes)).strftime(FMT)
        a.status = "SCHEDULED"
        events.append(a.appointment_id, "SCHEDULED", "REQUESTED", "SCHEDULED", decided, "ALLOCATOR")
        if wait > 0:
            excs.append(a.appointment_id, "SLOT_SHIFTED", cause, _severity(wait), decided, wait,
                        f"Requested {a.requested_start}, scheduled {a.scheduled_start}")
    return events, excs


def summarize(appts, excs, docks, dock_cal):
    """Measurable outputs. Everything is computed from the records, not stored separately."""
    sched = [a for a in appts if a.status == "SCHEDULED"]
    rej = [a for a in appts if a.status == "REJECTED"]
    delays = sorted(e.delay_minutes for e in excs if e.exception_type == "SLOT_SHIFTED")
    dtype = {d.dock_id: d.dock_type for d in docks}
    dfac = {d.dock_id: d.facility_id for d in docks}
    avail_by_type, avail_by_facday = Counter(), Counter()
    for c in dock_cal:
        avail_by_type[dtype[c.dock_id]] += c.available_minutes
        avail_by_facday[(dfac[c.dock_id], c.calendar_date)] += c.available_minutes
    used_by_type, used_by_facday = Counter(), Counter()
    for a in sched:
        used_by_type[dtype[a.dock_id]] += a.planned_duration_minutes
        used_by_facday[(a.facility_id, a.scheduled_start[:10])] += a.planned_duration_minutes
    util_fd = {k: used_by_facday[k] / v for k, v in avail_by_facday.items() if v}
    return {
        "scheduled": len(sched), "rejected": len(rej), "shifted": len(delays),
        "delay_avg": sum(delays) / len(delays) if delays else 0,
        "delay_p95": delays[int(0.95 * (len(delays) - 1))] if delays else 0,
        "delay_max": delays[-1] if delays else 0,
        "util_by_type": {t: used_by_type[t] / avail_by_type[t] for t in sorted(avail_by_type)},
        "util_overall": sum(used_by_type.values()) / sum(avail_by_type.values()),
        "facday_max": max(util_fd.values()), "facday_over80": sum(v > 0.8 for v in util_fd.values()),
        "facday_total": len(util_fd),
        "causes": dict(Counter(e.cause_code for e in excs)),
    }