"""models.py - one dataclass per entity = one row of one CSV.

Dates are ISO strings (YYYY-MM-DD) so export is trivial and deterministic.
Optional fields default to None (written as an empty cell).
effective_from / effective_to give each master row a validity window.
"""
from dataclasses import dataclass
from typing import Optional
 
 
@dataclass
class Facility:
    facility_id: str
    facility_name: str
    city: str
    timezone: str
    open_hour: int
    close_hour: int
    status: str
    effective_from: str
    effective_to: Optional[str] = None
 
 
@dataclass
class Dock:
    dock_id: str
    facility_id: str          # FK -> Facility (N:1)
    dock_number: int
    dock_type: str            # STANDARD / REEFER / HAZMAT_CERTIFIED
    dock_mode: str            # INBOUND / OUTBOUND / BOTH
    max_concurrent_trucks: int
    status: str
    effective_from: str
    effective_to: Optional[str] = None
 
 
@dataclass
class YardSlot:
    yard_slot_id: str
    facility_id: str          # FK -> Facility (N:1)
    slot_number: int
    slot_type: str            # STANDARD / REEFER_PLUG
    status: str
    effective_from: str
    effective_to: Optional[str] = None
 
 
@dataclass
class Carrier:
    carrier_id: str
    carrier_name: str
    scac_code: str
    status: str
    effective_from: str
    effective_to: Optional[str] = None
 
 
@dataclass
class Vehicle:
    vehicle_id: str
    carrier_id: str           # FK -> Carrier (N:1)
    vehicle_type: str
    plate_number: str
    is_refrigerated: bool
    hazmat_certified: bool
    capacity_pallets: int
    status: str
    effective_from: str
    effective_to: Optional[str] = None
 
 
@dataclass
class LaborShift:
    shift_id: str
    facility_id: str          # FK -> Facility (N:1)
    shift_date: str
    shift_code: str           # A / B
    start_time: str
    end_time: str
    crews_available: int      # crews = docks that can be worked at the same time
    status: str               # SCHEDULED / CANCELLED (cancelled = 0 usable crews)
 
 
@dataclass
class DockCalendar:
    calendar_id: str
    dock_id: str              # FK -> Dock (N:1); one row per dock per day
    calendar_date: str
    open_time: str
    close_time: str
    status: str               # OPEN / MAINTENANCE
    available_minutes: int    # DERIVED: (close-open)*60 if OPEN else 0
 
 
@dataclass
class HandlingRequirement:
    handling_req_id: str
    requirement_code: str
    description: str
    category: str             # LOAD_CLASS / ADD_ON
    load_type: Optional[str]  # None for add-ons (they apply to any load)
    fixed_minutes: int
    minutes_per_pallet: float
    temp_min_c: Optional[int] = None
    temp_max_c: Optional[int] = None
 
 
@dataclass
class Appointment:
    appointment_id: str
    facility_id: str          # FK -> Facility
    carrier_id: str           # FK -> Carrier
    vehicle_id: str           # FK -> Vehicle
    direction: str
    load_type: str
    request_created_at: str
    requested_start: str      # original request; NEVER overwritten by scheduling
    total_pallets: int        # DERIVED: sum of its shipments' pallets
    planned_duration_minutes: int   # DERIVED: from shipments' service minutes, rounded up to 30
    status: str
    dock_id: Optional[str] = None          # FK -> Dock, filled by the allocator
    yard_slot_id: Optional[str] = None     # FK -> YardSlot
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
 
 
@dataclass
class Shipment:
    shipment_id: str
    appointment_id: str       # FK -> Appointment (N:1)
    load_type: str
    pallets: int
    weight_kg: int
    service_minutes: int      # DERIVED: sum over its handling requirements
    status: str
 
 
@dataclass
class ShipmentHandling:
    """Bridge table for the Shipment <-> HandlingRequirement many-to-many."""
    shipment_id: str          # FK -> Shipment
    handling_req_id: str      # FK -> HandlingRequirement
 
 
@dataclass
class CheckInEvent:
    """Append-only lifecycle log: one row per state change of an appointment.
    (The task calls this entity CheckInEvent; it holds ALL lifecycle events.)"""
    event_id: str             # CHECK-<appointment_id>-NN
    appointment_id: str       # FK -> Appointment (N:1)
    event_seq: int            # 1, 2, 3 ... per appointment
    event_type: str
    from_status: Optional[str]
    to_status: str
    event_time: str
    source: str               # which system recorded it
 
 
@dataclass
class ExceptionRecord:
    """The task's 'Exception' entity (renamed to avoid shadowing Python's Exception)."""
    exception_id: str
    appointment_id: str       # FK -> Appointment (N:1, optional per appointment)
    exception_type: str
    cause_code: str
    severity: str
    detected_at: str
    delay_minutes: Optional[int]
    details: str
 
 
@dataclass
class GroundTruth:
    """One row per deliberately injected problem. Lives in its OWN folder and is never
    joined into the data tables, so it cannot leak into input features."""
    issue_id: str
    issue_type: str           # one of config.ANOMALY_TYPES
    table_name: str           # table that holds the anomalous record
    record_id: str            # primary key of that record
    related_record_id: Optional[str]
    field_name: str
    original_value: Optional[str]
    injected_value: Optional[str]
    detection_rule: str       # how a validator should be able to find it

#models: Blueprints file

"""
one dataclass per entity, and each one is a row of a CSV. 
The facility_id on a dock and the carrier_id on a vehicle are the 
foreign keys.
"""
