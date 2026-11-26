"""
simulation_models.py - Stage 10 Data Models & Enums
Holiday Closure Recovery & Timetable Simulation Engine
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Any, Set, Tuple
import hashlib
import json
from datetime import datetime, timezone

class ScenarioType:
    HOLIDAY = "HOLIDAY"
    INSTITUTIONAL_CLOSURE = "INSTITUTIONAL_CLOSURE"
    EMERGENCY_CLOSURE = "EMERGENCY_CLOSURE"
    CANCELLED_TEACHING_DAY = "CANCELLED_TEACHING_DAY"
    PARTIAL_DAY_CLOSURE = "PARTIAL_DAY_CLOSURE"
    ROOM_UNAVAILABLE = "ROOM_UNAVAILABLE"
    FACULTY_UNAVAILABLE = "FACULTY_UNAVAILABLE"
    SECTION_UNAVAILABLE = "SECTION_UNAVAILABLE"
    BUILDING_UNAVAILABLE = "BUILDING_UNAVAILABLE"
    CUSTOM_SCENARIO = "CUSTOM_SCENARIO"

class ScenarioSeverity:
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ScenarioStatus:
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class RecoveryMode:
    DIRECT_RESCHEDULE = "DIRECT_RESCHEDULE"
    DISTRIBUTED_RECOVERY = "DISTRIBUTED_RECOVERY"
    SAME_WEEK_RECOVERY = "SAME_WEEK_RECOVERY"
    EXTENDED_WINDOW_RECOVERY = "EXTENDED_WINDOW_RECOVERY"
    NO_RECOVERY = "NO_RECOVERY"

class RecoveryStatus:
    FULLY_RECOVERABLE = "FULLY_RECOVERABLE"
    PARTIALLY_RECOVERABLE = "PARTIALLY_RECOVERABLE"
    NOT_RECOVERABLE = "NOT_RECOVERABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"

def compute_hash(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

@dataclass
class DisruptionScenario:
    scenario_id: str
    scenario_type: str
    name: str
    description: str
    project_id: str
    source_project_version_id: str
    policy_snapshot_id: str
    created_by: str
    start_date: str = "2026-09-07"
    end_date: str = "2026-09-07"
    affected_dates: List[str] = field(default_factory=list)
    affected_days: List[int] = field(default_factory=list)      # 0 = Mon, 4 = Fri
    closed_slots: List[int] = field(default_factory=list)      # [0..8] or empty for full day
    affected_sections: List[str] = field(default_factory=list)
    affected_faculty: List[str] = field(default_factory=list)
    affected_rooms: List[str] = field(default_factory=list)
    affected_buildings: List[str] = field(default_factory=list)
    reason: str = "Unspecified closure"
    severity: str = ScenarioSeverity.MEDIUM
    status: str = ScenarioStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = compute_hash({
                "id": self.scenario_id,
                "type": self.scenario_type,
                "days": self.affected_days,
                "slots": self.closed_slots,
                "rooms": self.affected_rooms,
                "faculty": self.affected_faculty,
                "sections": self.affected_sections,
                "buildings": self.affected_buildings
            })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisruptionScenario":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class AffectedEvent:
    event_id: Any
    subject: str
    duration: int
    is_lab: bool
    is_shared: bool
    is_pinned: bool
    is_frozen: bool
    sections: List[str]
    faculty: List[str]
    room: str
    building: str
    original_day: int
    original_start_slot: int
    affected: bool = True
    lost_hours: int = 1
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AffectedEvent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class TeachingDeficit:
    affected_events_count: int = 0
    affected_event_hours: int = 0
    affected_section_hours: int = 0
    affected_faculty_hours: int = 0
    affected_room_hours: int = 0
    affected_labs: int = 0
    affected_shared_events: int = 0
    affected_multi_section_events: int = 0
    affected_multi_faculty_events: int = 0
    breakdown_by_day: Dict[int, int] = field(default_factory=dict)
    breakdown_by_section: Dict[str, int] = field(default_factory=dict)
    breakdown_by_faculty: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeachingDeficit":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class RecoveryCandidate:
    recovery_candidate_id: str
    scenario_id: str
    source_project_version_id: str
    source_timetable_fingerprint: str
    candidate_timetable_fingerprint: str
    recovery_mode: str
    generation_run_id: str
    affected_events_total: int = 0
    affected_events_recovered: int = 0
    affected_events_unrecovered: int = 0
    recovered_event_hours: int = 0
    unrecovered_event_hours: int = 0
    student_disruption_score: float = 0.0
    faculty_disruption_score: float = 0.0
    room_disruption_score: float = 0.0
    stability_score: float = 0.0
    gap_score: float = 0.0
    run_score: float = 0.0
    balance_score: float = 0.0
    late_start_score: float = 0.0
    early_finish_score: float = 0.0
    additional_break_score: float = 0.0
    hard_validation: Dict[str, Any] = field(default_factory=dict)
    soft_validation: Dict[str, Any] = field(default_factory=dict)
    status: str = "VALID"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryCandidate":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class SimulationResult:
    simulation_id: str
    source_project_id: str
    source_project_version_id: str
    source_timetable_fingerprint: str
    policy_snapshot_id: str
    scenario_ids: List[str]
    scenario_fingerprint: str
    feasibility_status: str
    affected_events: List[Dict[str, Any]]
    teaching_deficit: Dict[str, Any]
    recovery_status: str
    recovery_candidates: List[Dict[str, Any]]
    best_candidate: Optional[Dict[str, Any]]
    comparison: Dict[str, Any]
    diagnostics: Dict[str, Any]
    engine_versions: Dict[str, str]
    created_by: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_fingerprint: str = ""

    def __post_init__(self):
        if not self.result_fingerprint:
            self.result_fingerprint = compute_hash({
                "sim_id": self.simulation_id,
                "scenarios": self.scenario_ids,
                "deficit": self.teaching_deficit,
                "rec_status": self.recovery_status,
                "source_fp": self.source_timetable_fingerprint
            })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
