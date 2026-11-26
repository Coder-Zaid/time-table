"""
platform_models.py - Canonical Data Model, Project/Version Model & Schema Definitions
Stage 8.1: Timetable Creation Platform Foundation
Preserves the certified production timetable isolated as a read-only baseline.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict

# ------------------------------------------------------------------------------
# Enums & Literals
# ------------------------------------------------------------------------------

class ProjectStatus:
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY_FOR_GENERATION = "READY_FOR_GENERATION"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class SourceType:
    MANUAL = "MANUAL"
    CSV = "CSV"
    XLSX = "XLSX"
    FET_HTML = "FET_HTML"
    JSON = "JSON"
    IMPORTED_EXISTING = "IMPORTED_EXISTING"

class VersionType:
    RAW_IMPORT = "RAW_IMPORT"
    CANONICAL_BASELINE = "CANONICAL_BASELINE"
    SIMULATION = "SIMULATION"
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"

class EventType:
    THEORY = "THEORY"
    LAB = "LAB"
    TUTORIAL = "TUTORIAL"
    SEMINAR = "SEMINAR"
    OTHER = "OTHER"

class ExceptionType:
    INSTITUTION_HOLIDAY = "INSTITUTION_HOLIDAY"
    DEPARTMENT_CLOSURE = "DEPARTMENT_CLOSURE"
    SECTION_CLOSURE = "SECTION_CLOSURE"
    FACULTY_LEAVE = "FACULTY_LEAVE"
    ROOM_CLOSURE = "ROOM_CLOSURE"
    SPECIAL_NO_CLASS_PERIOD = "SPECIAL_NO_CLASS_PERIOD"

class ScopeType:
    INSTITUTION = "INSTITUTION"
    DEPARTMENT = "DEPARTMENT"
    SECTION = "SECTION"
    FACULTY = "FACULTY"
    ROOM = "ROOM"

class Severity:
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

# ------------------------------------------------------------------------------
# Canonical Data Models
# ------------------------------------------------------------------------------

@dataclass
class Institution:
    institution_id: str
    name: str
    timezone: str = "Asia/Kolkata"

@dataclass
class AcademicPeriod:
    academic_year: str
    semester: str
    start_date: str
    end_date: str

@dataclass
class SlotDefinition:
    slot_id: int
    day_id: int
    start_time: str
    end_time: str
    index: int
    is_teaching_slot: bool = True
    is_lunch: bool = False

@dataclass
class DayDefinition:
    day_id: int
    date: str
    day_name: str
    is_teaching_day: bool = True
    closure_reason: Optional[str] = None

@dataclass
class CalendarDefinition:
    calendar_id: str
    working_days: List[str]
    daily_start_time: str
    daily_end_time: str
    slot_duration_minutes: int
    lunch_policy: Dict[str, Any]
    special_closures: List[Dict[str, Any]] = field(default_factory=list)
    days: List[DayDefinition] = field(default_factory=list)
    slots: List[SlotDefinition] = field(default_factory=list)

@dataclass
class Section:
    section_id: str
    name: str
    program: str
    year: int
    semester: int
    department: str
    capacity: int = 60
    parent_section_id: Optional[str] = None

@dataclass
class StudentGroup:
    group_id: str
    section_id: str
    name: str
    capacity: int = 30

@dataclass
class Faculty:
    faculty_id: str
    name: str
    department: str
    email: str = ""
    active: bool = True

@dataclass
class Subject:
    subject_id: str
    code: str
    name: str
    department: str
    credits: int = 3
    active: bool = True

@dataclass
class Room:
    room_id: str
    name: str
    building: str
    floor: int
    capacity: int = 60
    room_type: str = "CLASSROOM"  # CLASSROOM, LAB, AUDITORIUM
    available: bool = True
    features: List[str] = field(default_factory=list)

@dataclass
class CourseRequirement:
    requirement_id: str
    subject_id: str
    section_id: str
    faculty_ids: List[str]
    theory_hours: int = 3
    lab_hours: int = 0
    weekly_hours: int = 3
    required_sessions: int = 3
    lab_duration: int = 2
    room_type_required: str = "CLASSROOM"
    room_capacity_required: int = 60
    is_shared: bool = False
    shared_section_ids: List[str] = field(default_factory=list)
    is_split: bool = False
    priority: int = 1

@dataclass
class Availability:
    availability_id: str
    entity_type: str  # FACULTY, SECTION, ROOM
    entity_id: str
    day_id: int
    slot_id: int
    status: str = "AVAILABLE"  # AVAILABLE, UNAVAILABLE, PREFERRED
    reason: Optional[str] = None

@dataclass
class CalendarException:
    exception_id: str
    scope: str  # INSTITUTION, DEPARTMENT, SECTION, FACULTY, ROOM
    scope_id: Optional[str]
    date: str
    start_slot: int
    end_slot: int
    exception_type: str  # INSTITUTION_HOLIDAY, etc.
    reason: str
    is_hard: bool = True

@dataclass
class ScheduledEvent:
    event_id: int
    subject_id: str
    subject: str
    event_type: str
    duration: int
    sections: List[str]
    faculty: List[str]
    room: str
    day_idx: int
    start_slot: int
    source_event_id: Optional[int] = None
    is_lab: bool = False
    is_shared: bool = False
    is_split: bool = False
    is_roomless: bool = False
    is_pinned: bool = False
    is_frozen: bool = False
    baseline_day: Optional[int] = None
    baseline_slot: Optional[int] = None
    baseline_room: Optional[str] = None

# ------------------------------------------------------------------------------
# Version & Project Container
# ------------------------------------------------------------------------------

@dataclass
class TimetableVersion:
    version_id: str
    project_id: str
    version_number: int
    version_type: str  # RAW_IMPORT, CANONICAL_BASELINE, SIMULATION, CANDIDATE, APPROVED, PUBLISHED
    created_at: str
    created_by: str
    description: str
    dataset: Dict[str, Any]
    events: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False

@dataclass
class TimetableProject:
    project_id: str
    project_name: str
    institution_name: str
    academic_year: str
    semester: str
    term_name: str
    timezone: str = "Asia/Kolkata"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = ProjectStatus.DRAFT
    source_type: str = SourceType.MANUAL
    source_version: Optional[str] = None
    active_version_id: Optional[str] = None
    versions: Dict[str, TimetableVersion] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def add_audit_entry(self, action: str, actor: str, details: Dict[str, Any]):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "details": details
        }
        self.audit_log.append(entry)
        self.updated_at = entry["timestamp"]

    def create_version(self, version_type: str, dataset: Dict[str, Any], created_by: str = "system", description: str = "") -> TimetableVersion:
        v_num = len(self.versions) + 1
        v_id = f"v{v_num}_{uuid.uuid4().hex[:8]}"
        new_v = TimetableVersion(
            version_id=v_id,
            project_id=self.project_id,
            version_number=v_num,
            version_type=version_type,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            description=description,
            dataset=dataset,
            is_active=True
        )
        # Deactivate old versions if this is active
        for v in self.versions.values():
            v.is_active = False
        self.versions[v_id] = new_v
        self.active_version_id = v_id
        self.add_audit_entry("CREATE_VERSION", created_by, {"version_id": v_id, "version_type": version_type})
        return new_v
