"""demand.py - the DEMAND side: appointment requests, their shipments and handling needs.

Order matters: appointment attributes are decided first (load type, carrier,
vehicle), then shipments inherit them, then durations are DERIVED from the
shipments. Nothing derived is drawn independently at random.
"""
import math
from datetime import datetime, timedelta
from itertools import accumulate

import ids
from calendars import day_list, hours_for
from config import (HANDLING_DEFS, CLASS_WEIGHTS, ADDON_PROB, LOAD_TYPES, DIRECTIONS,
                    LOAD_WEIGHTS, DIRECTION_WEIGHTS, WEEKDAY_DEMAND, PEAK_DAY_FRACTION,
                    PEAK_MULTIPLIER, SHIPMENTS_PER_APPT, PALLET_WEIGHT_KG, SLOT_MINUTES)
from models import HandlingRequirement, Appointment, Shipment, ShipmentHandling

FMT = "%Y-%m-%dT%H:%M"


def generate_handling_requirements():
    return [HandlingRequirement(handling_req_id=ids.handling_req_id(n), **d)
            for n, d in enumerate(HANDLING_DEFS, start=1)]


def _start_times(open_h, close_h):
    """Candidate request start times on a half-hour grid; last start is 1h before close."""
    t, out = float(open_h), []
    while t <= close_h - 1:
        out.append(t)
        t += 0.5
    return out


def _time_weight(t):
    """Two daily peaks (around 09:00 and 15:00) on top of a flat base -> congestion."""
    return 1 + 3.0 * math.exp(-((t - 9) / 1.5) ** 2) + 2.5 * math.exp(-((t - 15) / 1.5) ** 2)


def _vehicle_ok(vehicle, load_type):
    if load_type == "REFRIGERATED":
        return vehicle.is_refrigerated
    if load_type == "HAZARDOUS":
        return vehicle.hazmat_certified
    return vehicle.vehicle_type in ("DRY_VAN", "FLATBED")      # AMBIENT


def generate_demand(facilities, carriers, vehicles, handling_reqs, scale, rng):
    days = day_list(scale)

    # Which days are "peak congestion" days, and how busy each day is.
    n_peak = max(1, round(scale.days * PEAK_DAY_FRACTION))
    weekday_idx = [i for i, d in enumerate(days) if d.weekday() < 5]   # peaks only on Mon-Fri
    peak_idx = set(rng.sample(weekday_idx, n_peak))
    day_cum = list(accumulate(
        WEEKDAY_DEMAND[d.weekday()] * (PEAK_MULTIPLIER if i in peak_idx else 1.0)
        for i, d in enumerate(days)))

    n_fac = len(facilities)
    fac_w = [1.0] if n_fac == 1 else [1.3 - 0.6 * i / (n_fac - 1) for i in range(n_fac)]
    fac_cum = list(accumulate(fac_w))
    car_cum = list(accumulate(1 / (i + 1) ** 0.6 for i in range(len(carriers))))  # a few big carriers

    vehicles_by_carrier = {c.carrier_id: [] for c in carriers}
    for v in vehicles:
        vehicles_by_carrier[v.carrier_id].append(v)
    class_reqs = {lt: [h for h in handling_reqs if h.category == "LOAD_CLASS" and h.load_type == lt]
                  for lt in LOAD_TYPES}
    addons = [h for h in handling_reqs if h.category == "ADD_ON"]
    time_cache = {}

    raw = []
    for i in range(scale.appointments):
        fac = rng.choices(facilities, cum_weights=fac_cum)[0]
        day_i = rng.choices(range(scale.days), cum_weights=day_cum)[0]
        d = days[day_i]
        hours = hours_for(fac, d)
        if hours not in time_cache:
            ts = _start_times(*hours)
            time_cache[hours] = (ts, list(accumulate(_time_weight(t) for t in ts)))
        ts, ts_cum = time_cache[hours]
        t = rng.choices(ts, cum_weights=ts_cum)[0]
        start = datetime(d.year, d.month, d.day) + timedelta(hours=t)

        load = rng.choices(LOAD_TYPES, weights=LOAD_WEIGHTS)[0]
        direction = rng.choices(DIRECTIONS, weights=DIRECTION_WEIGHTS)[0]
        carrier = rng.choices(carriers, cum_weights=car_cum)[0]
        vehicle = rng.choice([v for v in vehicles_by_carrier[carrier.carrier_id]
                              if _vehicle_ok(v, load)])
        lead = timedelta(days=rng.randint(1, 7), hours=rng.randint(0, 6))

        n_ship = rng.choices(SHIPMENTS_PER_APPT[0], weights=SHIPMENTS_PER_APPT[1])[0]
        per_max = vehicle.capacity_pallets // n_ship          # total can never exceed truck capacity
        ships = []
        for _ in range(n_ship):
            pallets = rng.randint(max(2, per_max // 3), per_max)
            lo, hi = PALLET_WEIGHT_KG[load]
            weight = pallets * rng.randint(lo, hi)
            reqs = [rng.choices(class_reqs[load],
                                weights=[CLASS_WEIGHTS[h.requirement_code] for h in class_reqs[load]])[0]]
            for h in addons:
                if rng.random() < ADDON_PROB[h.requirement_code]:
                    reqs.append(h)
            minutes = math.ceil(sum(h.fixed_minutes + h.minutes_per_pallet * pallets for h in reqs))
            ships.append((pallets, weight, reqs, minutes))
        duration = math.ceil(sum(x[3] for x in ships) / SLOT_MINUTES) * SLOT_MINUTES
        end_of_day = datetime(d.year, d.month, d.day) + timedelta(hours=hours[1])
        if start + timedelta(minutes=duration) > end_of_day:    # carriers ask for windows that fit the day
            start = end_of_day - timedelta(minutes=duration)
        created = start - lead
        raw.append((start, fac.facility_id, i, carrier, vehicle, direction, load, created, ships))

    # IDs are assigned AFTER sorting, so APPT numbers run in chronological order.
    raw.sort(key=lambda r: (r[0], r[1], r[2]))

    appointments, shipments, bridge = [], [], []
    ship_counter = 0
    for n, (start, fac_id, _, carrier, vehicle, direction, load, created, ships) in enumerate(raw, start=1):
        appt_id = ids.appointment_id(n)
        total_service = sum(s[3] for s in ships)
        duration = math.ceil(total_service / SLOT_MINUTES) * SLOT_MINUTES     # derived, on the 30-min grid
        appointments.append(Appointment(
            appointment_id=appt_id, facility_id=fac_id, carrier_id=carrier.carrier_id,
            vehicle_id=vehicle.vehicle_id, direction=direction, load_type=load,
            request_created_at=created.strftime(FMT), requested_start=start.strftime(FMT),
            total_pallets=sum(s[0] for s in ships), planned_duration_minutes=duration,
            status="REQUESTED"))
        for pallets, weight, reqs, minutes in ships:
            ship_counter += 1
            sid = ids.shipment_id(ship_counter)
            shipments.append(Shipment(shipment_id=sid, appointment_id=appt_id, load_type=load,
                                      pallets=pallets, weight_kg=weight, service_minutes=minutes,
                                      status="PLANNED"))
            for h in reqs:
                bridge.append(ShipmentHandling(shipment_id=sid, handling_req_id=h.handling_req_id))
    peak_dates = [days[i].isoformat() for i in sorted(peak_idx)]
    return appointments, shipments, bridge, peak_dates