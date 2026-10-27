"""metrics.py - KPIs computed ONLY from the records (events, appointments, calendars).
Same data in -> same numbers out, which is what makes them reproducible."""
from collections import Counter, defaultdict
from datetime import datetime

from demand import FMT


def _pct(vals, p):
    return vals[int(p * (len(vals) - 1))] if vals else 0


def _stats(vals):
    v = sorted(vals)
    return {"n": len(v), "mean": round(sum(v) / len(v), 1) if v else 0,
            "median": _pct(v, 0.5), "p95": _pct(v, 0.95)}


def _mins(a, b):
    return int((a - b).total_seconds() // 60)


def compute_kpis(appts, events, docks, dock_cal, excs, peak_dates):
    times = defaultdict(dict)
    for e in events:
        times[e.appointment_id][e.event_type] = datetime.strptime(e.event_time, FMT)
    dtype = {d.dock_id: d.dock_type for d in docks}
    avail = Counter()
    for c in dock_cal:
        avail[dtype[c.dock_id]] += c.available_minutes

    used = Counter()
    wait, dwell, slot_delay = [], [], []
    wait_by_load, wait_peak, wait_off = defaultdict(list), [], []
    peak = set(peak_dates)
    for a in appts:
        if a.status != "COMPLETED":
            continue
        t = times[a.appointment_id]
        w = _mins(t["DOCK_STARTED"], t["CHECKED_IN"])
        wait.append(w)
        wait_by_load[a.load_type].append(w)
        (wait_peak if a.scheduled_start[:10] in peak else wait_off).append(w)
        dwell.append(_mins(t["DEPARTED"], t["CHECKED_IN"]))
        slot_delay.append(_mins(t["DOCK_STARTED"], datetime.strptime(a.scheduled_start, FMT)))
        used[dtype[a.dock_id]] += _mins(t["DOCK_COMPLETED"], t["DOCK_STARTED"])

    status = Counter(a.status for a in appts)
    shows = status["COMPLETED"] + status["NO_SHOW"]
    ex = Counter(e.exception_type for e in excs)
    return {
        "appointments_by_status": dict(sorted(status.items())),
        "events_total": len(events),
        "no_show_rate": round(status["NO_SHOW"] / shows, 4) if shows else 0,
        "early_arrival_rate": round(ex["EARLY_ARRIVAL"] / status["COMPLETED"], 4) if status["COMPLETED"] else 0,
        "on_time_dock_start_rate_15min": round(sum(d <= 15 for d in slot_delay) / len(slot_delay), 4) if slot_delay else 0,
        "wait_minutes_checkin_to_dock": _stats(wait),
        "wait_minutes_peak_days": _stats(wait_peak),
        "wait_minutes_other_days": _stats(wait_off),
        "wait_minutes_by_load": {k: _stats(v) for k, v in sorted(wait_by_load.items())},
        "dock_start_delay_vs_slot_minutes": _stats(slot_delay),
        "dwell_minutes_checkin_to_departure": _stats(dwell),
        "actual_dock_utilisation": {
            "overall": round(sum(used.values()) / sum(avail.values()), 4),
            **{t: round(used[t] / avail[t], 4) for t in sorted(avail)}},
        "exceptions_by_type": dict(sorted(ex.items())),
        "exceptions_by_cause": dict(sorted(Counter(e.cause_code for e in excs).items())),
    }