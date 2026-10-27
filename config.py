"""config.py - every tunable number and allowed value 
lives here.

Why: one place to change scale/rules, and validate.py can 
import the same
enums, so the generator and the validator can 
never disagree.
"""
from dataclasses import dataclass
from datetime import date
 
SEED = 20261022          # fixed seed -> identical output on every run
YEAR = 2026              # used in APPT-2026-..., SHP-2026-... IDs
START_DATE = date(2026, 8, 1)
 
 
@dataclass(frozen=True)
class Scale:
    """Size of a dataset. Starter and full use the SAME generator code."""
    facilities: int
    docks_per_facility: int
    appointments: int
    days: int
 
 
SCALES = {
    "starter": Scale(facilities=2, docks_per_facility=5, appointments=200, days=7),
    "full": Scale(facilities=10, docks_per_facility=10, appointments=20_000, days=60),
}
 
# ---- Allowed values (enums). validate.py checks data against these. ----
LOAD_TYPES = ["AMBIENT", "REFRIGERATED", "HAZARDOUS"]
DIRECTIONS = ["INBOUND", "OUTBOUND"]
DOCK_TYPES = ["STANDARD", "REEFER", "HAZMAT_CERTIFIED"]
VEHICLE_TYPES = ["DRY_VAN", "REEFER_TRUCK", "TANKER", "FLATBED"]
APPT_STATUSES = ["REQUESTED", "SCHEDULED", "CHECKED_IN", "AT_DOCK",
                 "SERVICED", "COMPLETED", "NO_SHOW", "CANCELLED", "REJECTED"]
# Cause codes for operational exceptions (allocator + simulator).
EXCEPTION_CAUSES = ["DOCK_CAPACITY_FULL", "LABOR_SHORTAGE", "DOCK_MAINTENANCE",
                    "OUTSIDE_OPERATING_HOURS", "YARD_FULL", "NO_WINDOW_IN_HORIZON",
                    "NO_SHOW", "EARLY_ARRIVAL", "DOCK_STILL_OCCUPIED"]
# Labels for the deliberately injected data anomalies (go in ground_truth, later).
ANOMALY_TYPES = ["DOCK_OVERLAP", "INCOMPATIBLE_LOAD", "CHECKIN_BEFORE_DATE",
                 "LABOR_SHIFT_UNAVAILABLE", "NO_SHOW_NOT_RECORDED"]
 
# Which dock types may handle which load (the compatibility rule).
COMPATIBLE_DOCKS = {
    "AMBIENT": ["STANDARD", "REEFER", "HAZMAT_CERTIFIED"],
    "REFRIGERATED": ["REEFER"],
    "HAZARDOUS": ["HAZMAT_CERTIFIED"],
}
 
# ---- Operating rules ----
OPEN_HOUR, CLOSE_HOUR = 6, 22     # dock open 06:00-22:00 = 16 h/day
SLOT_MINUTES = 30                 # appointments snap to a 30-min grid
 
# ---- Extra enums for master data ----
ENTITY_STATUSES = ["ACTIVE", "INACTIVE"]
DOCK_MODES = ["INBOUND", "OUTBOUND", "BOTH"]
YARD_SLOT_TYPES = ["STANDARD", "REEFER_PLUG"]
 
# ---- Labor / calendar rules ----
SUNDAY_HOURS = (8, 16)                 # reduced hours on Sundays
SHIFT_CODES = ["A", "B"]
SHIFT_STATUSES = ["SCHEDULED", "CANCELLED"]
CALENDAR_STATUSES = ["OPEN", "MAINTENANCE"]
SHIFT_CANCEL_RATE = 0.015              # ~1.5% of shifts cancelled (hook for the labor anomaly)
MAINTENANCE_RATE = 0.02                # ~2% of dock-days under maintenance
MIN_CREWS = 2
# crews_available = fraction of the facility's docks that can be worked at once
CREW_FRACTION = {"weekday": (0.6, 1.0), "saturday": (0.5, 0.8), "sunday": (0.4, 0.6)}
 
# ---- Handling requirements (reference data; service time = fixed + per_pallet * pallets) ----
REQ_CATEGORIES = ["LOAD_CLASS", "ADD_ON"]
HANDLING_DEFS = [
    dict(requirement_code="AMBIENT_STANDARD", description="Standard ambient freight",
         category="LOAD_CLASS", load_type="AMBIENT", fixed_minutes=15, minutes_per_pallet=3.0),
    dict(requirement_code="REEFER_CHILLED", description="Chilled goods, 2 to 8 C",
         category="LOAD_CLASS", load_type="REFRIGERATED", fixed_minutes=20, minutes_per_pallet=3.5,
         temp_min_c=2, temp_max_c=8),
    dict(requirement_code="REEFER_FROZEN", description="Frozen goods, -25 to -15 C",
         category="LOAD_CLASS", load_type="REFRIGERATED", fixed_minutes=25, minutes_per_pallet=4.0,
         temp_min_c=-25, temp_max_c=-15),
    dict(requirement_code="HAZMAT_FLAMMABLE", description="Flammable hazardous goods",
         category="LOAD_CLASS", load_type="HAZARDOUS", fixed_minutes=30, minutes_per_pallet=4.5),
    dict(requirement_code="HAZMAT_CORROSIVE", description="Corrosive hazardous goods",
         category="LOAD_CLASS", load_type="HAZARDOUS", fixed_minutes=35, minutes_per_pallet=5.0),
    dict(requirement_code="FRAGILE_HANDLING", description="Fragile goods, careful handling",
         category="ADD_ON", load_type=None, fixed_minutes=10, minutes_per_pallet=0.5),
    dict(requirement_code="HIGH_VALUE_SECURITY", description="High-value goods, security check",
         category="ADD_ON", load_type=None, fixed_minutes=15, minutes_per_pallet=0.0),
]
CLASS_WEIGHTS = {"AMBIENT_STANDARD": 100, "REEFER_CHILLED": 70, "REEFER_FROZEN": 30,
                 "HAZMAT_FLAMMABLE": 60, "HAZMAT_CORROSIVE": 40}
ADDON_PROB = {"FRAGILE_HANDLING": 0.12, "HIGH_VALUE_SECURITY": 0.05}
 
# ---- Demand shape ----
SHIPMENT_STATUSES = ["PLANNED", "COMPLETED", "NOT_HANDLED"]
LOAD_WEIGHTS = [75, 18, 7]             # order matches LOAD_TYPES
DIRECTION_WEIGHTS = [55, 45]           # order matches DIRECTIONS
WEEKDAY_DEMAND = [1.1, 1.1, 1.1, 1.1, 1.0, 0.6, 0.25]   # Mon..Sun
PEAK_DAY_FRACTION = 0.10               # ~10% of days are peak-congestion days
PEAK_MULTIPLIER = 2.0                  # peak days get 2x demand
SHIPMENTS_PER_APPT = ([1, 2, 3], [60, 30, 10])
PALLET_WEIGHT_KG = {"AMBIENT": (350, 550), "REFRIGERATED": (450, 650), "HAZARDOUS": (300, 500)}
 
# ---- Allocator rules ----
MAX_SHIFT_DAYS = 3             # a request may be pushed at most 3 days later, else REJECTED
OVERFLOW_AFTER_MINUTES = 120   # ambient loads may use reefer/hazmat docks only after waiting this long
YARD_BUFFER_SLOTS = 2          # truck holds a yard slot for the 60 min before its dock start
EVENT_TYPES = ["SCHEDULED", "REJECTED", "CHECKED_IN", "DOCK_STARTED",
               "DOCK_COMPLETED", "DEPARTED", "NO_SHOW"]
EVENT_SOURCES = ["ALLOCATOR", "GATE", "DOCK_OPS"]
EXCEPTION_TYPES = ["SLOT_SHIFTED", "UNSCHEDULABLE", "NO_SHOW", "EARLY_ARRIVAL", "CONGESTION_DELAY"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH"]
 
# ---- Lifecycle: the ONLY legal (from_status, to_status) pairs ----
LEGAL_TRANSITIONS = {
    ("REQUESTED", "SCHEDULED"), ("REQUESTED", "REJECTED"),
    ("SCHEDULED", "CHECKED_IN"), ("SCHEDULED", "NO_SHOW"), ("SCHEDULED", "CANCELLED"),
    ("CHECKED_IN", "AT_DOCK"), ("AT_DOCK", "SERVICED"), ("SERVICED", "COMPLETED"),
}
 
# ---- Simulation rules ----
NO_SHOW_RATE_RANGE = (0.01, 0.08)     # each carrier gets its own no-show probability in this range
NO_SHOW_GRACE_MINUTES = 60            # no-show is recorded this long after the slot start
EARLY_BIRD_PROB = 0.12                # share of trucks that turn up well before the slot
EARLY_BIRD_MINUTES = (30, 150)        # how early those trucks are
ARRIVAL_MEAN, ARRIVAL_SD = -3, 12     # everyone else: arrival offset ~ Normal(-3, 12) minutes
ARRIVAL_CLIP = (-25, 45)              # ...clipped, so normal arrivals are never "early" (<= -30)
EARLY_ARRIVAL_THRESHOLD = 30          # arriving >= 30 min early raises an EARLY_ARRIVAL exception
GATE_TO_DOCK_MINUTES = (5, 20)        # check-in -> truck positioned at dock
GATE_OUT_MINUTES = (5, 30)            # unloading done -> truck leaves the gate
SERVICE_FACTOR = (0.85, 1.35, 1.0)    # actual service = planned service * triangular(low, high, mode)
CONGESTION_THRESHOLD = 30             # dock still busy for >= 30 min raises CONGESTION_DELAY
 
# ---- Anomaly injection ----
ANOMALY_RATE = 0.002                  # each anomaly type hits ~0.2% of appointments (40 of 20,000)
MIN_PER_TYPE = 2                      # but at least 2 per type, even in the starter dataset
MAX_APPTS_PER_CANCELLED_SHIFT = 12    # keep the labor anomaly small and countable

##config.py: the settings file
"""
SEED = 20261022: the fixed seed from the task. Every random choice 
later will come from this number.
Scale: a small frozen dataclass holding the dataset size 
(facilities, docks per facility, appointments, days). The SCALES dict 
has two presets: starter (tiny, for fast testing) and 
full (10 facilities × 10 docks = 100 docks, 20,000 appointments, 
60 days). The task asks for the same generator to produce both, 
so you only ever change these numbers, never the logic.
The enums (LOAD_TYPES, DOCK_TYPES, APPT_STATUSES and so on): 
the “allowed values” from the data dictionary. validate.py will 
import these same lists, so the generator and the checker can’t disagree.
COMPATIBLE_DOCKS: the compatibility rule as data. 
Refrigerated loads can only go to REEFER docks and hazardous loads only 
to HAZMAT_CERTIFIED docks. Ambient loads can go anywhere. The allocator 
will read this table, and so will the anomaly injector when it 
deliberately breaks the rule.
Operating rules: docks are open 06:00–22:00 (16 hours) and 
appointments sit on a 30-minute grid.

"""