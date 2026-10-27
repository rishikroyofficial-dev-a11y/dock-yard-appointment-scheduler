"""events.py - append-only logs. Rows are only ever ADDED, never edited or deleted,
so the full history of every appointment is preserved."""
import ids
from config import LEGAL_TRANSITIONS
from models import CheckInEvent, ExceptionRecord
 
 
class EventLog:
    def __init__(self):
        self.rows = []
        self._seq, self._last_status, self._last_time = {}, {}, {}
 
    def append(self, appt_id, event_type, from_status, to_status, event_time, source):
        if from_status != self._last_status.get(appt_id, "REQUESTED"):
            raise ValueError(f"{appt_id}: from_status {from_status} does not follow the last event")
        if (from_status, to_status) not in LEGAL_TRANSITIONS:
            raise ValueError(f"{appt_id}: illegal transition {from_status} -> {to_status}")
        if event_time <= self._last_time.get(appt_id, ""):
            raise ValueError(f"{appt_id}: event_time {event_time} is not after the previous event")
        seq = self._seq.get(appt_id, 0) + 1
        self._seq[appt_id], self._last_status[appt_id], self._last_time[appt_id] = seq, to_status, event_time
        self.rows.append(CheckInEvent(
            event_id=ids.checkin_id(appt_id, seq), appointment_id=appt_id, event_seq=seq,
            event_type=event_type, from_status=from_status, to_status=to_status,
            event_time=event_time, source=source))
 
 
class ExceptionLog:
    def __init__(self):
        self.rows = []
 
    def append(self, appt_id, exc_type, cause, severity, detected_at, delay_minutes, details):
        self.rows.append(ExceptionRecord(
            exception_id=ids.exception_id(len(self.rows) + 1), appointment_id=appt_id,
            exception_type=exc_type, cause_code=cause, severity=severity,
            detected_at=detected_at, delay_minutes=delay_minutes, details=details))