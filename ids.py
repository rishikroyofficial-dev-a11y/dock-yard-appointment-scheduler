"""ids.py - the ONLY place IDs are built. Zero-padded, deterministic, immutable.

IDs are pure functions of counters/parent IDs - no randomness - so the same
seed always yields the same IDs, and child IDs embed their parent's ID.
"""
import re
from config import YEAR
 
 
def facility_id(n: int) -> str:            # FAC-001
    return f"FAC-{n:03d}"
 
def dock_id(fac_id: str, n: int) -> str:   # DOCK-FAC-001-001
    return f"DOCK-{fac_id}-{n:03d}"
 
def yard_slot_id(fac_id: str, n: int) -> str:    # YARD-FAC-001-001 (my choice)
    return f"YARD-{fac_id}-{n:03d}"
 
def carrier_id(n: int) -> str:             # CAR-001 (my choice)
    return f"CAR-{n:03d}"
 
def vehicle_id(n: int) -> str:             # VEH-00001 (my choice)
    return f"VEH-{n:05d}"
 
def appointment_id(n: int) -> str:         # APPT-2026-000001
    return f"APPT-{YEAR}-{n:06d}"
 
def shipment_id(n: int) -> str:            # SHP-2026-000001
    return f"SHP-{YEAR}-{n:06d}"
 
def checkin_id(appt_id: str, seq: int) -> str:   # CHECK-APPT-2026-000001-01
    return f"CHECK-{appt_id}-{seq:02d}"
 
def labor_shift_id(fac_id: str, day: str, shift: str) -> str:  # SHIFT-FAC-001-2026-08-01-A
    return f"SHIFT-{fac_id}-{day}-{shift}"
 
def handling_req_id(n: int) -> str:        # HR-001 (my choice)
    return f"HR-{n:03d}"
 
def calendar_id(dock: str, day) -> str:   # CAL-DOCK-FAC-001-001-20260801 (my choice)
    return f"CAL-{dock}-{day:%Y%m%d}"
 
def ground_truth_id(n: int) -> str:      # GT-000001 (my choice)
    return f"GT-{n:06d}"
 
def exception_id(n: int) -> str:           # EXC-2026-000001 (my choice)
    return f"EXC-{YEAR}-{n:06d}"
 
 
# Regex for each ID type; validate.py will use these to catch malformed IDs.
PATTERNS = {
    "facility": r"^FAC-\d{3}$",
    "dock": r"^DOCK-FAC-\d{3}-\d{3}$",
    "yard_slot": r"^YARD-FAC-\d{3}-\d{3}$",
    "carrier": r"^CAR-\d{3}$",
    "vehicle": r"^VEH-\d{5}$",
    "appointment": r"^APPT-\d{4}-\d{6}$",
    "shipment": r"^SHP-\d{4}-\d{6}$",
    "checkin": r"^CHECK-APPT-\d{4}-\d{6}-\d{2}$",
    "labor_shift": r"^SHIFT-FAC-\d{3}-\d{4}-\d{2}-\d{2}-[A-Z]$",
    "handling_req": r"^HR-\d{3}$",
    "exception": r"^EXC-\d{4}-\d{6}$",
    "calendar": r"^CAL-DOCK-FAC-\d{3}-\d{3}-\d{8}$",
    "ground_truth": r"^GT-\d{6}$",
}
 
def is_valid(kind: str, value: str) -> bool:
    return re.match(PATTERNS[kind], value) is not None


#ids.py: the ID factory
"""
Each function is a pure function: the same input always gives the same ID, with no randomness. 
That is what makes IDs deterministic and immutable.
f"{n:03d}" means “format the integer as 3 digits, zero-padded”, so 7 becomes 007.
Child IDs embed the parent ID (DOCK-FAC-001-001, CHECK-APPT-2026-000001-01). 
You can read the lineage straight off the ID, and mismatched references are easy to catch.
PATTERNS and is_valid() hold a regex per ID type, which validate.py will use to catch malformed IDs. 
In a regex, ^ and $ anchor the whole string and \d{3} means exactly three digits.
"""