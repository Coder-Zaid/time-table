"""
generation_models.py - Core Data Models, Enums, and Schemas for Stage 9
Timetable Generation & Optimization Engine
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple

class GenerationStatus:
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    INFEASIBLE_GENERATION = "INFEASIBLE_GENERATION"
    GENERATION_FAILED = "GENERATION_FAILED"
    TIME_LIMIT = "TIME_LIMIT"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"

class GenerationProfile:
    FEASIBILITY_FIRST = "FEASIBILITY_FIRST"
    BALANCED = "BALANCED"
    QUALITY_FIRST = "QUALITY_FIRST"
    STABILITY_FIRST = "STABILITY_FIRST"

@dataclass
class GenerationConfig:
    generation_run_id: str
    seed: int = 42
    candidate_count: int = 1
    time_limit_seconds: int = 120
    optimization_profile: str = GenerationProfile.BALANCED
    preserve_existing_assignments: bool = True
    allow_rearrangement: bool = True
    respect_pinned_events: bool = True
    respect_frozen_events: bool = True
    max_backtracks: int = 5000

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class PlacementDomain:
    event_id: Any
    legal_placements: List[Tuple[int, int]] = field(default_factory=list) # (day, start_slot)
    placement_count: int = 0
    blocked_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class QualityScore:
    hard_violation_count: int = 0
    soft_violation_count: int = 0
    preference_violation_count: int = 0
    weighted_soft_penalty: float = 0.0
    weighted_preference_penalty: float = 0.0
    gap_score: float = 0.0
    run_score: float = 0.0
    balance_score: float = 0.0
    lunch_score: float = 0.0
    stability_score: float = 0.0
    overall_quality_score: float = 0.0
    late_start_score: float = 0.0
    early_finish_score: float = 0.0
    additional_break_score: float = 0.0
    p0_hard: int = 0
    p1_critical: int = 0
    p2_runs_gaps: float = 0.0
    p3_balance: float = 0.0
    p4_break_quality: float = 0.0
    p5_late_start: float = 0.0
    p6_early_finish: float = 0.0
    p7_other: float = 0.0
    p8_stability: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def lexicographic_tuple(self) -> Tuple:
        return (
            self.hard_violation_count,
            self.p1_critical,
            self.p2_runs_gaps,
            self.p3_balance,
            self.p4_break_quality,
            self.p5_late_start,
            self.p6_early_finish,
            self.p7_other,
            self.p8_stability
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lexicographic_tuple"] = list(self.lexicographic_tuple())
        return d

@dataclass
class TimetableCandidate:
    candidate_id: str
    generation_run_id: str
    candidate_index: int
    project_id: str
    project_version_id: str
    policy_snapshot_id: str
    feasibility_run_id: str
    engine_version: str = "9.0.0"
    seed: int = 42
    is_valid: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)
    score: QualityScore = field(default_factory=QualityScore)
    validation_report: Dict[str, Any] = field(default_factory=dict)
    candidate_fingerprint: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

@dataclass
class GenerationStatistics:
    events_total: int = 0
    events_movable: int = 0
    events_pinned: int = 0
    events_frozen: int = 0
    domain_generation_time_ms: float = 0.0
    construction_time_ms: float = 0.0
    optimization_time_ms: float = 0.0
    validation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    placements_attempted: int = 0
    placements_accepted: int = 0
    placements_rejected: int = 0
    backtracks: int = 0
    max_backtrack_depth: int = 0
    dead_ends: int = 0
    hard_conflicts_detected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class GenerationDiagnostics:
    unplaced_events: List[Any] = field(default_factory=list)
    bottleneck_events: List[Any] = field(default_factory=list)
    hard_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    resource_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    availability_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    closure_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    synchronization_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    room_capacity_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    policy_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    search_statistics: Dict[str, Any] = field(default_factory=dict)
    termination_reason: str = "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class GenerationResult:
    generation_run_id: str
    project_id: str
    project_version_id: str
    policy_snapshot_id: str
    feasibility_run_id: str
    engine_version: str = "9.0.0"
    seed: int = 42
    configuration: Dict[str, Any] = field(default_factory=dict)
    status: str = GenerationStatus.READY
    termination_reason: str = "SUCCESS"
    candidate_count_requested: int = 1
    candidate_count_generated: int = 0
    candidate_count_valid: int = 0
    selected_candidate_id: Optional[str] = None
    selected_candidate: Optional[Dict[str, Any]] = None
    candidates_summary: List[Dict[str, Any]] = field(default_factory=list)
    generation_statistics: GenerationStatistics = field(default_factory=GenerationStatistics)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    optimization_summary: Dict[str, Any] = field(default_factory=dict)
    comparison_summary: Dict[str, Any] = field(default_factory=dict)
    diagnostics: GenerationDiagnostics = field(default_factory=GenerationDiagnostics)
    input_fingerprint: str = ""
    result_fingerprint: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    executed_by_user_id: str = "usr_system"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def compute_model_fingerprint(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
