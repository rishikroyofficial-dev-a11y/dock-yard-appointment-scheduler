"""calendars.py - the SUPPLY side: when docks are open and 
how many crews work.

Labor shifts and dock capacity calendars are generated for 
every day of the window, so the allocator can 
later check "is this dock open, and is a crew free?"
"""
from datetime import timedelta

import ids
from config import (START_DATE, SUNDAY_HOURS, MAINTENANCE_RATE, SHIFT_CANCEL_RATE,
                    CREW_FRACTION, MIN_CREWS)
from models import LaborShift, DockCalendar


def day_list(scale):
    return [START_DATE + timedelta(days=i) for i in range(scale.days)]


def hours_for(fac, d):
    """Opening hours of a facility on date d (Sundays are shorter)."""
    return SUNDAY_HOURS if d.weekday() == 6 else (fac.open_hour, fac.close_hour)


def _hhmm(h):
    return f"{h:02d}:00"


def generate_labor_shifts(facilities, scale, rng):
    rows = []
    for fac in facilities:
        for d in day_list(scale):
            open_h, close_h = hours_for(fac, d)
            if d.weekday() == 6:                       # Sunday: one shift
                shifts, key = [("A", open_h, close_h)], "sunday"
            else:                                      # otherwise split the day in two
                mid = open_h + (close_h - open_h) // 2
                shifts = [("A", open_h, mid), ("B", mid, close_h)]
                key = "saturday" if d.weekday() == 5 else "weekday"
            for code, start, end in shifts:
                lo, hi = CREW_FRACTION[key]
                crews = max(MIN_CREWS, round(rng.uniform(lo, hi) * scale.docks_per_facility))
                status = "CANCELLED" if rng.random() < SHIFT_CANCEL_RATE else "SCHEDULED"
                rows.append(LaborShift(
                    shift_id=ids.labor_shift_id(fac.facility_id, d.isoformat(), code),
                    facility_id=fac.facility_id, shift_date=d.isoformat(), shift_code=code,
                    start_time=_hhmm(start), end_time=_hhmm(end),
                    crews_available=crews, status=status))
    return rows


def generate_dock_calendars(facilities, docks, scale, rng):
    fac_by_id = {f.facility_id: f for f in facilities}
    rows = []
    for dock in docks:
        fac = fac_by_id[dock.facility_id]
        for d in day_list(scale):
            open_h, close_h = hours_for(fac, d)
            status = "MAINTENANCE" if rng.random() < MAINTENANCE_RATE else "OPEN"
            minutes = (close_h - open_h) * 60 if status == "OPEN" else 0   # derived value
            rows.append(DockCalendar(
                calendar_id=ids.calendar_id(dock.dock_id, d), dock_id=dock.dock_id,
                calendar_date=d.isoformat(), open_time=_hhmm(open_h), close_time=_hhmm(close_h),
                status=status, available_minutes=minutes))
    return rows