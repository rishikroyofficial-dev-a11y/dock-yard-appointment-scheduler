"""schema.py - the single description of the data model: tables, keys, enums.
validate.py (and later the SQL exporter) read this, so nothing is defined twice."""
from config import (ENTITY_STATUSES, DOCK_TYPES, DOCK_MODES, YARD_SLOT_TYPES, VEHICLE_TYPES,
                    SHIFT_CODES, SHIFT_STATUSES, CALENDAR_STATUSES, REQ_CATEGORIES, LOAD_TYPES,
                    DIRECTIONS, APPT_STATUSES, SHIPMENT_STATUSES, EVENT_TYPES, EVENT_SOURCES,
                    EXCEPTION_TYPES, EXCEPTION_CAUSES, SEVERITIES)
from models import (Facility, Dock, YardSlot, Carrier, Vehicle, LaborShift, DockCalendar,
                    HandlingRequirement, Appointment, Shipment, ShipmentHandling,
                    CheckInEvent, ExceptionRecord)

# Parents before children.
TABLES = {
    "facilities": Facility, "carriers": Carrier, "handling_requirements": HandlingRequirement,
    "docks": Dock, "yard_slots": YardSlot, "vehicles": Vehicle, "labor_shifts": LaborShift,
    "dock_calendar": DockCalendar, "appointments": Appointment, "shipments": Shipment,
    "shipment_handling": ShipmentHandling, "checkin_events": CheckInEvent, "exceptions": ExceptionRecord,
}
PRIMARY_KEYS = {
    "facilities": ["facility_id"], "carriers": ["carrier_id"], "handling_requirements": ["handling_req_id"],
    "docks": ["dock_id"], "yard_slots": ["yard_slot_id"], "vehicles": ["vehicle_id"],
    "labor_shifts": ["shift_id"], "dock_calendar": ["calendar_id"], "appointments": ["appointment_id"],
    "shipments": ["shipment_id"], "shipment_handling": ["shipment_id", "handling_req_id"],
    "checkin_events": ["event_id"], "exceptions": ["exception_id"],
}
# (child table, child column, parent table, parent column)
FOREIGN_KEYS = [
    ("docks", "facility_id", "facilities", "facility_id"),
    ("yard_slots", "facility_id", "facilities", "facility_id"),
    ("vehicles", "carrier_id", "carriers", "carrier_id"),
    ("labor_shifts", "facility_id", "facilities", "facility_id"),
    ("dock_calendar", "dock_id", "docks", "dock_id"),
    ("appointments", "facility_id", "facilities", "facility_id"),
    ("appointments", "carrier_id", "carriers", "carrier_id"),
    ("appointments", "vehicle_id", "vehicles", "vehicle_id"),
    ("appointments", "dock_id", "docks", "dock_id"),               # optional until scheduled
    ("appointments", "yard_slot_id", "yard_slots", "yard_slot_id"),  # optional
    ("shipments", "appointment_id", "appointments", "appointment_id"),
    ("shipment_handling", "shipment_id", "shipments", "shipment_id"),
    ("shipment_handling", "handling_req_id", "handling_requirements", "handling_req_id"),
    ("checkin_events", "appointment_id", "appointments", "appointment_id"),
    ("exceptions", "appointment_id", "appointments", "appointment_id"),
]
ID_KIND = {"facilities": "facility", "carriers": "carrier", "handling_requirements": "handling_req",
           "docks": "dock", "yard_slots": "yard_slot", "vehicles": "vehicle", "labor_shifts": "labor_shift",
           "dock_calendar": "calendar", "appointments": "appointment", "shipments": "shipment",
           "checkin_events": "checkin", "exceptions": "exception"}
ENUMS = {
    ("facilities", "status"): ENTITY_STATUSES, ("docks", "dock_type"): DOCK_TYPES,
    ("docks", "dock_mode"): DOCK_MODES, ("docks", "status"): ENTITY_STATUSES,
    ("yard_slots", "slot_type"): YARD_SLOT_TYPES, ("yard_slots", "status"): ENTITY_STATUSES,
    ("carriers", "status"): ENTITY_STATUSES, ("vehicles", "vehicle_type"): VEHICLE_TYPES,
    ("vehicles", "status"): ENTITY_STATUSES, ("labor_shifts", "shift_code"): SHIFT_CODES,
    ("labor_shifts", "status"): SHIFT_STATUSES, ("dock_calendar", "status"): CALENDAR_STATUSES,
    ("handling_requirements", "category"): REQ_CATEGORIES, ("handling_requirements", "load_type"): LOAD_TYPES,
    ("appointments", "direction"): DIRECTIONS, ("appointments", "load_type"): LOAD_TYPES,
    ("appointments", "status"): APPT_STATUSES, ("shipments", "load_type"): LOAD_TYPES,
    ("shipments", "status"): SHIPMENT_STATUSES, ("checkin_events", "event_type"): EVENT_TYPES,
    ("checkin_events", "from_status"): APPT_STATUSES, ("checkin_events", "to_status"): APPT_STATUSES,
    ("checkin_events", "source"): EVENT_SOURCES, ("exceptions", "exception_type"): EXCEPTION_TYPES,
    ("exceptions", "cause_code"): EXCEPTION_CAUSES, ("exceptions", "severity"): SEVERITIES,
}
# Columns (or column groups) that must be unique besides the primary key.
NATURAL_KEYS = {
    "facilities": [["facility_name"]], "carriers": [["scac_code"], ["carrier_name"]],
    "handling_requirements": [["requirement_code"]], "docks": [["facility_id", "dock_number"]],
    "yard_slots": [["facility_id", "slot_number"]], "vehicles": [["plate_number"]],
    "labor_shifts": [["facility_id", "shift_date", "shift_code"]],
    "dock_calendar": [["dock_id", "calendar_date"]],
    "checkin_events": [["appointment_id", "event_seq"], ["appointment_id", "event_type"]],
}
# Which appointment status each event type leads to.
EVENT_TO_STATUS = {"SCHEDULED": "SCHEDULED", "REJECTED": "REJECTED", "CHECKED_IN": "CHECKED_IN",
                   "DOCK_STARTED": "AT_DOCK", "DOCK_COMPLETED": "SERVICED", "DEPARTED": "COMPLETED",
                   "NO_SHOW": "NO_SHOW"}