"""
versioning_models.py - Stage 11 Data Models & Schemas
Review, Versioning & Approval Workflow
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

def compute_hash(data: Any) -> str:
    """Computes a deterministic SHA-256 fingerprint for arbitrary JSON-serializable data."""
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

class VersionState:
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    IN_REVIEW = "IN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"

class ReviewStatus:
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class ReviewDecision:
    APPROVE_FOR_APPROVAL = "APPROVE_FOR_APPROVAL"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"

class CommentSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"

class CommentStatus:
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"

class ChangeRequestStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    IMPLEMENTED = "IMPLEMENTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class ChangeRequestPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKING = "BLOCKING"

class ApprovalDecision:
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

# State permissions contract
VERSION_STATE_CAPABILITIES = {
    VersionState.DRAFT: {"editable": True, "reviewable": False, "approvable": False},
    VersionState.VALIDATING: {"editable": False, "reviewable": False, "approvable": False},
    VersionState.READY_FOR_REVIEW: {"editable": False, "reviewable": True, "approvable": False},
    VersionState.IN_REVIEW: {"editable": False, "reviewable": True, "approvable": False},
    VersionState.CHANGES_REQUESTED: {"editable": False, "reviewable": True, "approvable": False},
    VersionState.READY_FOR_APPROVAL: {"editable": False, "reviewable": True, "approvable": True},
    VersionState.APPROVED: {"editable": False, "reviewable": True, "approvable": False},
    VersionState.SUPERSEDED: {"editable": False, "reviewable": True, "approvable": False},
    VersionState.ARCHIVED: {"editable": False, "reviewable": True, "approvable": False},
}

# Allowed workflow transitions
ALLOWED_TRANSITIONS = {
    (VersionState.DRAFT, VersionState.VALIDATING),
    (VersionState.VALIDATING, VersionState.READY_FOR_REVIEW),
    (VersionState.VALIDATING, VersionState.DRAFT),
    (VersionState.READY_FOR_REVIEW, VersionState.IN_REVIEW),
    (VersionState.IN_REVIEW, VersionState.CHANGES_REQUESTED),
    (VersionState.IN_REVIEW, VersionState.READY_FOR_APPROVAL),
    (VersionState.CHANGES_REQUESTED, VersionState.DRAFT),
    (VersionState.CHANGES_REQUESTED, VersionState.IN_REVIEW),
    (VersionState.READY_FOR_APPROVAL, VersionState.APPROVED),
    (VersionState.READY_FOR_APPROVAL, VersionState.CHANGES_REQUESTED),
    (VersionState.APPROVED, VersionState.SUPERSEDED),
    (VersionState.SUPERSEDED, VersionState.ARCHIVED),
    (VersionState.DRAFT, VersionState.ARCHIVED)
}

@dataclass
class TimetableVersion:
    version_id: str
    project_id: str
    parent_version_id: Optional[str]
    version_number: int
    version_label: str
    status: str
    source_type: str
    source_generation_run_id: Optional[str]
    source_simulation_id: Optional[str]
    source_manual_edit_session_id: Optional[str]
    timetable_fingerprint: str
    canonical_dataset_fingerprint: str
    policy_snapshot_id: str
    feasibility_run_id: Optional[str]
    validation_run_id: Optional[str]
    created_by: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    locked_at: Optional[str] = None
    approved_at: Optional[str] = None
    superseded_at: Optional[str] = None
    archived_at: Optional[str] = None
    change_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimetableVersion":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class ReviewComment:
    comment_id: str
    review_id: str
    version_id: str
    event_id: Optional[Any]
    section_id: Optional[str]
    faculty_id: Optional[str]
    room_id: Optional[str]
    author_user_id: str
    body: str
    severity: str = CommentSeverity.INFO
    status: str = CommentStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewComment":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class ChangeRequest:
    change_request_id: str
    project_id: str
    source_version_id: str
    target_version_id: Optional[str]
    requested_by: str
    assigned_to: Optional[str]
    reason: str
    priority: str = ChangeRequestPriority.MEDIUM
    status: str = ChangeRequestStatus.OPEN
    affected_event_ids: List[Any] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeRequest":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class ReviewRecord:
    review_id: str
    project_id: str
    version_id: str
    reviewer_user_id: str
    reviewer_role: str
    status: str = ReviewStatus.NOT_STARTED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: str = ""
    decision: Optional[str] = None
    validation_snapshot_id: Optional[str] = None
    feasibility_snapshot_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    comments: List[Dict[str, Any]] = field(default_factory=list)
    change_requests: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class ApprovalRecord:
    approval_id: str
    project_id: str
    version_id: str
    approver_user_id: str
    approver_role: str
    decision: str
    decision_reason: str
    validation_run_id: str
    feasibility_run_id: Optional[str]
    review_id: str
    version_fingerprint: str
    approved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revoked_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class EventMovement:
    old_day: Optional[int]
    new_day: Optional[int]
    old_slot: Optional[int]
    new_slot: Optional[int]
    old_room: Optional[str]
    new_room: Optional[str]
    old_duration: Optional[int]
    new_duration: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class EventDiff:
    event_id: Any
    subject: str
    change_type: str  # ADDED, REMOVED, MOVED, UNCHANGED
    movement: Optional[EventMovement] = None
    faculty_changed: bool = False
    section_changed: bool = False
    room_changed: bool = False
    duration_changed: bool = False
    is_lab: bool = False
    is_shared: bool = False
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class DiffSummary:
    events_added: int = 0
    events_removed: int = 0
    events_moved: int = 0
    rooms_changed: int = 0
    faculty_changed: int = 0
    sections_changed: int = 0
    total_slot_displacement: int = 0
    day_changes: int = 0
    hard_conflicts_before: int = 0
    hard_conflicts_after: int = 0
    soft_metric_changes: Dict[str, Any] = field(default_factory=dict)
    event_diffs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
