"""master_data.py - Step 2: parent/master tables, generated FIRST.

Each generator takes the Scale and (where randomness is needed) a seeded
random.Random, and returns a list of dataclass rows. Children are built from
their parents' IDs, so every foreign key is valid by construction.
"""
from config import (OPEN_HOUR, CLOSE_HOUR, VEHICLE_TYPES)
import ids
from models import Facility, Dock, YardSlot, Carrier, Vehicle

MASTER_EFFECTIVE_FROM = "2025-01-01"   # all master data is valid before the 60-day window

CITIES = ["Kolkata", "Mumbai", "Delhi", "Chennai", "Hyderabad",
          "Bengaluru", "Pune", "Ahmedabad", "Jaipur", "Lucknow"]

CARRIER_PREFIXES = ["Blue Ridge", "Swift", "Eastern", "Highway", "Metro", "Prime",
                    "Delta", "Summit", "Coastal", "Apex", "Northern", "Silverline",
                    "Redwood", "Pioneer", "Orbit", "Titan", "Horizon", "Keystone",
                    "Falcon", "Vanguard"]
CARRIER_SUFFIXES = ["Freight", "Logistics", "Transport", "Carriers"]

# Vehicle mix: mostly dry vans, some reefers, few tankers/flatbeds.
VEHICLE_WEIGHTS = [60, 20, 10, 10]                       # order matches VEHICLE_TYPES
PALLET_CAPACITY = {"DRY_VAN": 26, "REEFER_TRUCK": 24, "TANKER": 18, "FLATBED": 20}


def generate_facilities(scale):
    assert scale.facilities <= len(CITIES), "add more cities to CITIES"
    rows = []
    for n in range(1, scale.facilities + 1):
        city = CITIES[n - 1]
        rows.append(Facility(
            facility_id=ids.facility_id(n),
            facility_name=f"{city} Distribution Center",
            city=city, timezone="Asia/Kolkata",
            open_hour=OPEN_HOUR, close_hour=CLOSE_HOUR,
            status="ACTIVE", effective_from=MASTER_EFFECTIVE_FROM))
    return rows


def generate_docks(facilities, scale, rng):
    n = scale.docks_per_facility
    assert n >= 3, "need >=3 docks per facility for one of each dock type"
    n_reefer = max(1, round(0.2 * n))        # ~20% reefer docks
    n_haz = max(1, round(0.2 * n))           # ~20% hazmat-certified docks
    n_std = n - n_reefer - n_haz             # the rest standard
    types = ["STANDARD"] * n_std + ["REEFER"] * n_reefer + ["HAZMAT_CERTIFIED"] * n_haz

    rows = []
    for fac in facilities:
        for i, dock_type in enumerate(types, start=1):
            # Special docks are BOTH-mode so refrigerated/hazardous loads are
            # always schedulable in either direction. Only standard docks vary.
            if dock_type == "STANDARD":
                mode = rng.choices(["BOTH", "INBOUND", "OUTBOUND"], weights=[70, 15, 15])[0]
            else:
                mode = "BOTH"
            rows.append(Dock(
                dock_id=ids.dock_id(fac.facility_id, i),
                facility_id=fac.facility_id, dock_number=i,
                dock_type=dock_type, dock_mode=mode, max_concurrent_trucks=1,
                status="ACTIVE", effective_from=MASTER_EFFECTIVE_FROM))
    return rows


def generate_yard_slots(facilities, scale):
    count = scale.docks_per_facility * 2     # waiting yard = 2x number of docks
    n_plug = max(1, round(0.2 * count))      # ~20% have reefer power plugs
    rows = []
    for fac in facilities:
        for i in range(1, count + 1):
            slot_type = "REEFER_PLUG" if i > count - n_plug else "STANDARD"
            rows.append(YardSlot(
                yard_slot_id=ids.yard_slot_id(fac.facility_id, i),
                facility_id=fac.facility_id, slot_number=i, slot_type=slot_type,
                status="ACTIVE", effective_from=MASTER_EFFECTIVE_FROM))
    return rows


def generate_carriers(scale):
    count = max(5, scale.appointments // 1000)
    assert count <= len(CARRIER_PREFIXES) * len(CARRIER_SUFFIXES)
    rows = []
    for i in range(count):
        prefix = CARRIER_PREFIXES[i % len(CARRIER_PREFIXES)]
        suffix = CARRIER_SUFFIXES[(i // len(CARRIER_PREFIXES)) % len(CARRIER_SUFFIXES)]
        # Unique 4-letter code: 'C' + the index written in base-26 letters.
        scac = "C" + chr(65 + (i // 676) % 26) + chr(65 + (i // 26) % 26) + chr(65 + i % 26)
        rows.append(Carrier(
            carrier_id=ids.carrier_id(i + 1), carrier_name=f"{prefix} {suffix}",
            scac_code=scac, status="ACTIVE", effective_from=MASTER_EFFECTIVE_FROM))
    return rows


def generate_vehicles(carriers, rng):
    rows, counter = [], 0
    for car in carriers:
        fleet = rng.randint(4, 10)
        # First three vehicles are forced so EVERY carrier can serve ambient,
        # refrigerated and hazardous loads (no unschedulable carriers).
        types = ["DRY_VAN", "REEFER_TRUCK", "TANKER"]
        types += rng.choices(VEHICLE_TYPES, weights=VEHICLE_WEIGHTS, k=fleet - 3)
        for vtype in types:
            counter += 1
            hazmat = (vtype == "TANKER") or (vtype == "DRY_VAN" and rng.random() < 0.15)
            rows.append(Vehicle(
                vehicle_id=ids.vehicle_id(counter), carrier_id=car.carrier_id,
                vehicle_type=vtype, plate_number=f"MH{(counter % 40) + 1:02d}-{counter:04d}",
                is_refrigerated=(vtype == "REEFER_TRUCK"), hazmat_certified=hazmat,
                capacity_pallets=PALLET_CAPACITY[vtype],
                status="ACTIVE", effective_from=MASTER_EFFECTIVE_FROM))
    return rows



#master_data: Foundations file

"""
master_data.py: five generator functions, parents first. 
Docks are built by looping over facilities and 
vehicles by looping over carriers, so a child can only 
ever reference a parent that exists.

"""