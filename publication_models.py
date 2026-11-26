"""
publication_models.py - Stage 12 Data Models & Schemas
Publishing + Public Timetable Viewer

Principle: Publication is a snapshot operation, never a live mutable reference to an editable timetable.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

def compute_hash(data: Any) -> str:
    """Computes a deterministic SHA-256 fingerprint for arbitrary JSON-serializable data."""
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

class PublicationStatus:
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    UNPUBLISHED = "UNPUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"

class Visibility:
    PUBLIC = "PUBLIC"
    UNLISTED = "UNLISTED"

@dataclass
class PublicEvent:
    """
    Client/public-safe timetable event projection.
    Strictly excludes internal IDs, policy weights, generation diagnostics, audit records, or review comments.
    """
    event_id: str
    subject_name: str
    faculty_name: str
    section_name: str
    room_name: str
    building: str
    floor: str
    day: int                 # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday
    day_name: str            # Monday, Tuesday, etc.
    start_time: str          # e.g., "09:00" or "09:00 AM"
    end_time: str            # e.g., "11:00" or "11:00 AM"
    duration_hours: int      # 1 or 2 (labs render as 2)
    event_type: str          # THEORY or LAB
    is_lab: bool = False
    is_shared: bool = False
    shared_sections: List[str] = field(default_factory=list)
    multi_faculty: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublicEvent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class PublicationRecord:
    """
    Isolated, immutable publication metadata record.
    Preserves full provenance linking to the source approved version without mutating it.
    """
    publication_id: str
    public_identifier: str
    public_slug: str
    project_id: str
    source_version_id: str
    source_version_number: int
    source_version_fingerprint: str
    source_policy_snapshot_id: str
    source_feasibility_run_id: Optional[str]
    source_validation_fingerprint: Optional[str]
    published_at: str
    published_by: str
    status: str = PublicationStatus.PUBLISHED
    visibility: str = Visibility.PUBLIC
    title: str = "Academic Timetable"
    description: str = ""
    institution_name: str = "Woxsen University"
    academic_period: str = "Spring 2026"
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    superseded_by: Optional[str] = None
    unpublished_at: Optional[str] = None
    unpublished_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublicationRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class PublicTimetableSnapshot:
    """
    Complete immutable public snapshot containing all sanitized public events,
    summary counts, calendar days, time slots, and entity lookup listings.
    """
    publication_id: str
    public_slug: str
    title: str
    institution_name: str
    academic_period: str
    effective_from: Optional[str]
    effective_to: Optional[str]
    published_at: str
    total_events: int
    total_student_hours: int
    total_faculty_hours: int
    total_labs: int
    total_shared_events: int
    total_no_room_events: int
    sections: List[str]
    faculties: List[str]
    rooms: List[str]
    subjects: List[str]
    days: List[Dict[str, Any]]
    time_slots: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    fingerprint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublicTimetableSnapshot":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
