"""
policy_engine.py - Production-Grade Policy, Constraint, and Rule Architecture
Stage 8.5: Constraint & Policy Builder

Modules:
- PolicyCategory: HARD, SOFT, PREFERENCE
- PolicyScope: PROJECT, SECTION, STUDENT_GROUP, FACULTY, SUBJECT, ROOM, EVENT, DAY, SLOT, EVENT_TYPE
- RuleRegistry: Central registry of all supported rule types with schemas, defaults, and category support
- PolicyModel & PolicyVersion: Immutable versioning and attribution
- PolicyValidator: Deep semantic conflict detection (contradictory rules, min > max, impossible hours)
- PolicyRepository & PolicyVersionService: Draft management, activation, rollbacks
- PolicyImpactAnalyzer: Pre-activation simulation preview without optimization or timetable mutation
- PolicyAuthorizationService & PolicyAuditService: Server-side RBAC and append-only audit trail
"""

import os
import copy
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict

import auth_service
from auth_service import User, UserRole, AuditEventType

class PolicyCategory:
    HARD = "HARD"
    SOFT = "SOFT"
    PREFERENCE = "PREFERENCE"

class PolicyScope:
    PROJECT = "PROJECT"
    SECTION = "SECTION"
    STUDENT_GROUP = "STUDENT_GROUP"
    FACULTY = "FACULTY"
    SUBJECT = "SUBJECT"
    ROOM = "ROOM"
    EVENT = "EVENT"
    DAY = "DAY"
    SLOT = "SLOT"
    EVENT_TYPE = "EVENT_TYPE"

class PolicyStatus:
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class PolicySource:
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
    IMPORTED = "IMPORTED"
    USER_DEFINED = "USER_DEFINED"

@dataclass
class PolicyModel:
    policy_id: str
    policy_version_id: str
    project_id: str
    name: str
    description: str
    category: str # HARD | SOFT | PREFERENCE
    rule_type: str
    scope: str
    target_ids: List[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 1000
    weight: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    effective_from_version: str = "v1"
    created_by_user_id: str = "usr_admin_001"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = PolicyStatus.ACTIVE
    source: str = PolicySource.SYSTEM_DEFAULT
    reason: Optional[str] = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class RuleDefinition:
    rule_type: str
    display_name: str
    description: str
    category_support: List[str]
    scope_support: List[str]
    parameter_schema: Dict[str, Any]
    default_category: str
    default_parameters: Dict[str, Any]
    documentation: str

class RuleRegistry:
    """
    Central repository of all institutional scheduling rule types and parameter schemas.
    """
    def __init__(self):
        self._rules: Dict[str, RuleDefinition] = {}
        self._register_rules()

    def register(self, rule: RuleDefinition):
        self._rules[rule.rule_type] = rule

    def get(self, rule_type: str) -> Optional[RuleDefinition]:
        return self._rules.get(rule_type)

    def list_all(self) -> List[RuleDefinition]:
        return list(self._rules.values())

    def _register_rules(self):
        rules = [
            RuleDefinition("NO_SECTION_CONFLICT", "Section Overlap Protection", "Prevents a section from having multiple simultaneous classes.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.SECTION], {}, PolicyCategory.HARD, {}, "Enforces that student cohorts are never double-booked."),
            RuleDefinition("NO_FACULTY_CONFLICT", "Faculty Overlap Protection", "Prevents faculty from teaching multiple simultaneous classes.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.FACULTY], {}, PolicyCategory.HARD, {}, "Enforces single teaching location per faculty at any slot."),
            RuleDefinition("NO_ROOM_CONFLICT", "Physical Room Overlap Protection", "Prevents double-booking physical room spaces.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.ROOM], {}, PolicyCategory.HARD, {}, "Ensures one event per room space."),
            RuleDefinition("FACULTY_AVAILABILITY", "Faculty Availability", "Restricts faculty to available working windows.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.FACULTY], {"available_slots": list}, PolicyCategory.HARD, {"available_slots": []}, "Faculty working window bounds."),
            RuleDefinition("SECTION_AVAILABILITY", "Section Availability", "Restricts student section to available schedule windows.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.SECTION], {"available_slots": list}, PolicyCategory.HARD, {"available_slots": []}, "Section availability window."),
            RuleDefinition("ROOM_AVAILABILITY", "Room Availability", "Defines operational availability for rooms.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.ROOM], {"available_slots": list}, PolicyCategory.HARD, {"available_slots": []}, "Room maintenance and operational hours."),
            RuleDefinition("CALENDAR_CLOSURE", "Institutional Calendar Closure", "Designates specific days and slots as closed for scheduling.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.DAY, PolicyScope.SLOT], {"days": list, "slots": list, "reason": str}, PolicyCategory.HARD, {"days": [4], "slots": [4, 5, 6, 7, 8], "reason": "Post-Lunch Closure"}, "Hard institutional closure (e.g. Friday post-lunch)."),
            RuleDefinition("WORKING_HOURS", "Institutional Working Hours", "Defines the daily scheduling slot boundary.", [PolicyCategory.HARD], [PolicyScope.PROJECT], {"days": list, "allowed_start_slot": int, "allowed_end_slot": int}, PolicyCategory.HARD, {"days": [0, 1, 2, 3, 4], "allowed_start_slot": 0, "allowed_end_slot": 8}, "Operational hours 09:00 - 18:00."),
            RuleDefinition("EVENT_DURATION", "Event Duration Bounds", "Enforces duration boundaries on teaching sessions.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.EVENT_TYPE], {"min_duration": int, "max_duration": int}, PolicyCategory.HARD, {"min_duration": 1, "max_duration": 2}, "Session length validation."),
            RuleDefinition("LAB_CONTIGUITY", "Lab Session Contiguity", "Requires laboratory sessions to span consecutive slots.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.EVENT_TYPE], {"required_duration": int}, PolicyCategory.HARD, {"required_duration": 2}, "Labs must remain contiguous."),
            RuleDefinition("LAB_SAME_ROOM", "Lab Same Room Preservation", "Ensures a lab remains in a single assigned lab room.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.ROOM], {}, PolicyCategory.HARD, {}, "Preserves lab physical location."),
            RuleDefinition("SHARED_EVENT_SYNCHRONIZATION", "Shared Event Synchronization", "Requires linked cohort sections to move synchronously.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.EVENT], {}, PolicyCategory.HARD, {}, "Maintains synchronization for combined batches."),
            RuleDefinition("MULTI_FACULTY_SYNCHRONIZATION", "Multi-Faculty Synchronization", "Maintains synchronization for co-taught courses.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.FACULTY], {}, PolicyCategory.HARD, {}, "Team-taught course synchronization."),
            RuleDefinition("MULTI_SECTION_SYNCHRONIZATION", "Multi-Section Synchronization", "Maintains synchronization across combined sections.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.SECTION], {}, PolicyCategory.HARD, {}, "Combined section synchronization."),
            RuleDefinition("SPLIT_EVENT_PARENT_COLLISION", "Split Event Collision Protection", "Prevents parent cohort collisions with subgroup sessions.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.STUDENT_GROUP], {}, PolicyCategory.HARD, {}, "Subgroup hierarchy protection."),
            RuleDefinition("PINNED_EVENT_PROTECTION", "Pinned Event Protection", "Prevents manual or automated movement of pinned events.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.EVENT], {}, PolicyCategory.HARD, {}, "Pinned schedule protection."),
            RuleDefinition("FROZEN_EVENT_PROTECTION", "Frozen Event Protection", "Protects immutable frozen events from all mutations.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.EVENT], {}, PolicyCategory.HARD, {}, "Frozen schedule protection."),
            RuleDefinition("BLOCKED_TIME", "Time Blocking Policy", "Allows administrator to block time slots across scopes.", [PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.SECTION, PolicyScope.FACULTY, PolicyScope.ROOM], {"day": int, "start_slot": int, "duration": int, "reason": str}, PolicyCategory.HARD, {"day": 0, "start_slot": 0, "duration": 1, "reason": "Blocked"}, "Manual time reservation."),
            RuleDefinition("MAX_DAILY_HOURS_SECTION", "Max Daily Teaching Hours (Section)", "Caps total student hours per day.", [PolicyCategory.SOFT, PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.SECTION], {"max_hours": (int, float)}, PolicyCategory.SOFT, {"max_hours": 6}, "Student study load limit."),
            RuleDefinition("MAX_DAILY_HOURS_FACULTY", "Max Daily Teaching Hours (Faculty)", "Caps faculty lecture hours per day.", [PolicyCategory.SOFT, PolicyCategory.HARD], [PolicyScope.PROJECT, PolicyScope.FACULTY], {"max_hours": (int, float)}, PolicyCategory.SOFT, {"max_hours": 6}, "Faculty daily teaching limit."),
            RuleDefinition("MIN_DAILY_HOURS_SECTION", "Min Daily Teaching Hours (Section)", "Ensures reasonable daily student engagement.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT, PolicyScope.SECTION], {"min_hours": (int, float)}, PolicyCategory.SOFT, {"min_hours": 2}, "Minimum daily cohort engagement."),
            RuleDefinition("MIN_DAILY_HOURS_FACULTY", "Min Daily Teaching Hours (Faculty)", "Ensures minimum teaching load on active days.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT, PolicyScope.FACULTY], {"min_hours": (int, float)}, PolicyCategory.SOFT, {"min_hours": 1}, "Faculty minimum active daily load."),
            RuleDefinition("MAX_CONSECUTIVE_HOURS_SECTION", "Max Consecutive Hours (Section)", "Limits consecutive teaching without a break.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT, PolicyScope.SECTION], {"max_hours": int}, PolicyCategory.SOFT, {"max_hours": 3}, "Student cognitive endurance limit."),
            RuleDefinition("MAX_CONSECUTIVE_HOURS_FACULTY", "Max Consecutive Hours (Faculty)", "Limits continuous teaching hours for instructors.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT, PolicyScope.FACULTY], {"max_hours": int}, PolicyCategory.SOFT, {"max_hours": 3}, "Faculty continuous lecture limit."),
            RuleDefinition("EXACT_CONSECUTIVE_HOURS_SECTION", "Exact Consecutive Hours (Section)", "Enforces exact continuous learning blocks.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.SECTION], {"target_hours": int}, PolicyCategory.SOFT, {"target_hours": 2}, "Exact block size."),
            RuleDefinition("EXACT_CONSECUTIVE_HOURS_FACULTY", "Exact Consecutive Hours (Faculty)", "Enforces exact teaching block sizes.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.FACULTY], {"target_hours": int}, PolicyCategory.SOFT, {"target_hours": 2}, "Exact faculty block."),
            RuleDefinition("LUNCH_WINDOW", "Institutional Lunch Window", "Guarantees a break window around midday.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT], {"start_slot": int, "end_slot": int, "required_break_hours": (int, float)}, PolicyCategory.SOFT, {"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0}, "Midday break assurance."),
            RuleDefinition("LUNCH_BREAK", "Dedicated Lunch Break", "Designates specific slot as designated lunch hour.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.PROJECT], {"slots": list}, PolicyCategory.SOFT, {"slots": [4]}, "Standard 13:00 - 14:00 lunch hour."),
            RuleDefinition("MAX_DAILY_EVENTS_SECTION", "Max Daily Events (Section)", "Limits number of distinct subjects/classes per day.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.SECTION], {"max_events": int}, PolicyCategory.SOFT, {"max_events": 4}, "Prevents fragmented cohort schedules."),
            RuleDefinition("MAX_DAILY_EVENTS_FACULTY", "Max Daily Events (Faculty)", "Limits number of distinct classes per faculty day.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.FACULTY], {"max_events": int}, PolicyCategory.SOFT, {"max_events": 3}, "Prevents excessive context switching."),
            RuleDefinition("MIN_GAP_SECTION", "Minimum Gap Between Events (Section)", "Enforces buffer slots between sessions.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.SECTION], {"min_gap_slots": int}, PolicyCategory.SOFT, {"min_gap_slots": 0}, "Buffer time between student classes."),
            RuleDefinition("MIN_GAP_FACULTY", "Minimum Gap Between Events (Faculty)", "Enforces buffer slots between teaching blocks.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.FACULTY], {"min_gap_slots": int}, PolicyCategory.SOFT, {"min_gap_slots": 0}, "Buffer time for faculty transit and prep."),
            RuleDefinition("DAY_BALANCE_SECTION", "Daily Load Balance (Section)", "Minimizes variance in daily hours across the week.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.SECTION], {"max_difference_hours": (int, float)}, PolicyCategory.SOFT, {"max_difference_hours": 2.0}, "Even weekly workload distribution."),
            RuleDefinition("DAY_BALANCE_FACULTY", "Daily Load Balance (Faculty)", "Balances teaching loads across working days.", [PolicyCategory.SOFT, PolicyCategory.PREFERENCE], [PolicyScope.FACULTY], {"max_difference_hours": (int, float)}, PolicyCategory.SOFT, {"max_difference_hours": 2.0}, "Balances faculty weekly distribution."),
            RuleDefinition("PREFERRED_DAYS", "Preferred Teaching Days", "Rewards scheduling on designated preferred days.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.FACULTY, PolicyScope.SECTION, PolicyScope.DAY], {"days": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"days": [0, 1, 2], "weight": 5.0}, "Faculty day preference."),
            RuleDefinition("FORBIDDEN_DAYS", "Forbidden Days", "Restricts scheduling on specific days of the week.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.FACULTY, PolicyScope.SECTION, PolicyScope.DAY], {"days": list}, PolicyCategory.HARD, {"days": []}, "Off-day designation."),
            RuleDefinition("PREFERRED_SLOTS", "Preferred Slots", "Rewards placement in optimal morning or afternoon slots.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.FACULTY, PolicyScope.SECTION, PolicyScope.SUBJECT, PolicyScope.SLOT], {"slots": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"slots": [1, 2], "weight": 5.0}, "Time-of-day preference."),
            RuleDefinition("FORBIDDEN_SLOTS", "Forbidden Slots", "Excludes specific slots from allocation.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.FACULTY, PolicyScope.SECTION, PolicyScope.SLOT], {"slots": list}, PolicyCategory.HARD, {"slots": []}, "Unavailable slot exclusion."),
            RuleDefinition("PREFERRED_ROOMS", "Preferred Room Allocation", "Directs sessions to specialized or proximate rooms.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.SUBJECT, PolicyScope.FACULTY, PolicyScope.ROOM], {"room_ids": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"room_ids": [], "weight": 5.0}, "Room affinity."),
            RuleDefinition("FORBIDDEN_ROOMS", "Forbidden Rooms", "Bars session types from incompatible rooms.", [PolicyCategory.HARD, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.SUBJECT, PolicyScope.EVENT_TYPE, PolicyScope.ROOM], {"room_ids": list}, PolicyCategory.HARD, {"room_ids": []}, "Room type restriction."),
            RuleDefinition("PREFERRED_FACULTY_SLOTS", "Preferred Faculty Slots", "Faculty personal timeslot affinity.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.FACULTY], {"preferred_slots": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"preferred_slots": [0, 1, 2], "weight": 5.0}, "Faculty morning/afternoon preference."),
            RuleDefinition("FACULTY_TIME_PREFERENCE", "Faculty Time Preference", "Complex faculty day and slot affinity with weight.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.FACULTY], {"faculty_id": str, "preferred_days": list, "preferred_slots": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"faculty_id": "", "preferred_days": [0, 1], "preferred_slots": [1, 2], "weight": 10.0}, "Granular faculty availability preference."),
            RuleDefinition("SECTION_TIME_PREFERENCE", "Section Time Preference", "Section specific preferred scheduling windows.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.SECTION], {"section_id": str, "preferred_days": list, "preferred_slots": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"section_id": "", "preferred_days": [0, 1, 2, 3], "preferred_slots": [0, 1, 2, 3], "weight": 10.0}, "Student cohort time preference."),
            RuleDefinition("ROOM_PREFERENCE", "Room Feature Preference", "Matches room capabilities with event type.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.ROOM], {"room_id": str, "preferred_event_types": list, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"room_id": "", "preferred_event_types": ["LAB"], "weight": 8.0}, "Lab equipment room matching."),
            RuleDefinition("STABILITY_AGAINST_BASELINE", "Baseline Schedule Stability", "Penalizes unnecessary deviations from prior timetable baseline.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT], {"enabled": bool, "weight": (int, float)}, PolicyCategory.PREFERENCE, {"enabled": True, "weight": 20.0}, "Minimizes disruption across timetable iterations."),
            RuleDefinition("PREF_LATE_START", "Late Start Preference", "Strongly prefers scheduling daily sessions to start later in the usable teaching day.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.SECTION, PolicyScope.STUDENT_GROUP, PolicyScope.FACULTY], {"preferred_start_slot": int}, PolicyCategory.PREFERENCE, {"enabled": True, "priority": "HIGH", "preferred_start_slot": 1, "weight": 1.0}, "Optimizes daily start times by preferring later first teaching slot."),
            RuleDefinition("PREF_ADDITIONAL_BREAK", "Additional Break Preference", "Prefers at least 1 additional hour of free time beyond the mandatory 1-hour break (target 2+ hours).", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.SECTION, PolicyScope.STUDENT_GROUP, PolicyScope.FACULTY], {"preferred_total_free_hours": int, "additional_break_hours": int}, PolicyCategory.PREFERENCE, {"enabled": True, "priority": "HIGH", "preferred_total_free_hours": 2, "additional_break_hours": 1, "weight": 1.0}, "Guarantees existing 1h break and prefers additional free non-teaching hours without artificial gap fragmentation."),
            RuleDefinition("PREF_EARLY_FINISH", "Early Finish Preference", "Prefers schedules whose final daily class finishes earlier, ranked below late start.", [PolicyCategory.PREFERENCE, PolicyCategory.SOFT], [PolicyScope.PROJECT, PolicyScope.SECTION, PolicyScope.STUDENT_GROUP, PolicyScope.FACULTY], {"preferred_finish_slot": int}, PolicyCategory.PREFERENCE, {"enabled": True, "priority": "MEDIUM", "preferred_finish_slot": 7, "weight": 0.7}, "Encourages earlier completion of teaching day while deferring to late start and break quality.")
        ]
        for r in rules:
            self.register(r)

GLOBAL_RULE_REGISTRY = RuleRegistry()

# ------------------------------------------------------------------------------
# Built-In Policy Templates
# ------------------------------------------------------------------------------

def get_default_university_policies(project_id: str) -> List[PolicyModel]:
    pols = [
        PolicyModel(f"pol_{project_id}_no_sec", "v1", project_id, "No Section Overlap", "Sections cannot have overlapping sessions", PolicyCategory.HARD, "NO_SECTION_CONFLICT", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_no_fac", "v1", project_id, "No Faculty Overlap", "Faculty cannot have overlapping sessions", PolicyCategory.HARD, "NO_FACULTY_CONFLICT", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_no_room", "v1", project_id, "No Room Overlap", "Rooms cannot have overlapping sessions", PolicyCategory.HARD, "NO_ROOM_CONFLICT", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_work_hrs", "v1", project_id, "Working Hours (09:00 - 18:00)", "Operational slot boundary 0 to 8", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.PROJECT, priority=1000, parameters={"days": [0, 1, 2, 3, 4], "allowed_start_slot": 0, "allowed_end_slot": 8}),
        PolicyModel(f"pol_{project_id}_lab_cont", "v1", project_id, "Lab Contiguity", "Lab sessions require contiguous 2 hours", PolicyCategory.HARD, "LAB_CONTIGUITY", PolicyScope.PROJECT, priority=1000, parameters={"required_duration": 2}),
        PolicyModel(f"pol_{project_id}_lab_room", "v1", project_id, "Lab Same Room", "Labs must remain in same designated room", PolicyCategory.HARD, "LAB_SAME_ROOM", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_shared_syn", "v1", project_id, "Shared Event Synchronization", "Combined sections move together", PolicyCategory.HARD, "SHARED_EVENT_SYNCHRONIZATION", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_pinned", "v1", project_id, "Pinned Event Protection", "Pinned sessions cannot be relocated", PolicyCategory.HARD, "PINNED_EVENT_PROTECTION", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_frozen", "v1", project_id, "Frozen Event Protection", "Frozen sessions cannot be altered", PolicyCategory.HARD, "FROZEN_EVENT_PROTECTION", PolicyScope.PROJECT, priority=1000),
        PolicyModel(f"pol_{project_id}_blocked", "v1", project_id, "Time Blocking Protection", "Blocked time reservations cannot be scheduled on", PolicyCategory.HARD, "BLOCKED_TIME", PolicyScope.PROJECT, priority=1000, parameters={"day": 0, "start_slot": 0, "duration": 1, "reason": "Institutional Maintenance"}),
        PolicyModel(f"pol_{project_id}_lunch_win", "v1", project_id, "Lunch Window Quality", "Midday break between 13:00 and 14:00", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, priority=500, weight=10.0, parameters={"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0}),
        PolicyModel(f"pol_{project_id}_max_consec", "v1", project_id, "Max Consecutive Hours", "Limit student runs to 3 consecutive hours", PolicyCategory.SOFT, "MAX_CONSECUTIVE_HOURS_SECTION", PolicyScope.PROJECT, priority=500, weight=5.0, parameters={"max_hours": 3}),
        PolicyModel(f"pol_{project_id}_pref_late_start", "v1", project_id, "Late Start Priority", "Strongly prefers later start to teaching day", PolicyCategory.PREFERENCE, "PREF_LATE_START", PolicyScope.PROJECT, priority=600, weight=1.0, parameters={"enabled": True, "priority": "HIGH", "preferred_start_slot": 1, "weight": 1.0}),
        PolicyModel(f"pol_{project_id}_pref_add_break", "v1", project_id, "Additional Break Preference", "Preserves 1h mandatory break and prefers >= 1h additional free time (target 2h total)", PolicyCategory.PREFERENCE, "PREF_ADDITIONAL_BREAK", PolicyScope.PROJECT, priority=650, weight=1.0, parameters={"enabled": True, "priority": "HIGH", "preferred_total_free_hours": 2, "additional_break_hours": 1, "weight": 1.0}),
        PolicyModel(f"pol_{project_id}_pref_early_finish", "v1", project_id, "Early Finish Preference", "Prefers earlier daily completion after late start and breaks", PolicyCategory.PREFERENCE, "PREF_EARLY_FINISH", PolicyScope.PROJECT, priority=450, weight=0.7, parameters={"enabled": True, "priority": "MEDIUM", "preferred_finish_slot": 7, "weight": 0.7})
    ]
    return pols

def get_woxsen_certified_profile(project_id: str) -> List[PolicyModel]:
    base = get_default_university_policies(project_id)
    # Institutional Friday Post-Lunch Hard Closure: Slots 4-8 (13:00 - 18:00)
    friday_closure = PolicyModel(
        policy_id=f"pol_{project_id}_fri_close",
        policy_version_id="v1",
        project_id=project_id,
        name="Friday Post-Lunch Hard Closure",
        description="Institutional Friday closure for sports and faculty meetings (Slots 4 to 8 / 01:00 PM - 06:00 PM)",
        category=PolicyCategory.HARD,
        rule_type="CALENDAR_CLOSURE",
        scope=PolicyScope.PROJECT,
        priority=1000,
        parameters={"days": [4], "slots": [4, 5, 6, 7, 8], "reason": "Certified Example Profile: Friday Post-Lunch Closure"}
    )
    base.append(friday_closure)
    return base

def get_optimization_preferences_profile(project_id: str) -> List[PolicyModel]:
    return [
        PolicyModel(
            f"pol_{project_id}_pref_late_start", "v1", project_id,
            "Late Start Priority", "Strongly prefers later start to teaching day",
            PolicyCategory.PREFERENCE, "PREF_LATE_START", PolicyScope.PROJECT,
            priority=600, weight=1.0,
            parameters={"enabled": True, "priority": "HIGH", "preferred_start_slot": 1, "weight": 1.0}
        ),
        PolicyModel(
            f"pol_{project_id}_pref_add_break", "v1", project_id,
            "Additional Break Preference", "Preserves 1h mandatory break and prefers >= 1h additional free time (target 2h total)",
            PolicyCategory.PREFERENCE, "PREF_ADDITIONAL_BREAK", PolicyScope.PROJECT,
            priority=650, weight=1.0,
            parameters={"enabled": True, "priority": "HIGH", "preferred_total_free_hours": 2, "additional_break_hours": 1, "weight": 1.0}
        ),
        PolicyModel(
            f"pol_{project_id}_pref_early_finish", "v1", project_id,
            "Early Finish Preference", "Prefers earlier daily completion after late start and breaks",
            PolicyCategory.PREFERENCE, "PREF_EARLY_FINISH", PolicyScope.PROJECT,
            priority=450, weight=0.7,
            parameters={"enabled": True, "priority": "MEDIUM", "preferred_finish_slot": 7, "weight": 0.7}
        )
    ]

# ------------------------------------------------------------------------------
# Policy Validator & Deep Conflict Engine
# ------------------------------------------------------------------------------

@dataclass
class PolicyValidationResult:
    valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    affected_rules: List[str] = field(default_factory=list)
    affected_entities: List[str] = field(default_factory=list)
    estimated_schedule_impact: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class PolicyValidator:
    """
    Validates a set of policies for internal consistency, contradictions,
    unsupported configurations, and schema compliance prior to activation.
    """
    def __init__(self, registry: Optional[RuleRegistry] = None):
        self.registry = registry or GLOBAL_RULE_REGISTRY

    def validate_policy(self, policy: PolicyModel) -> Tuple[bool, List[str]]:
        errors = []
        rule_def = self.registry.get(policy.rule_type)
        if not rule_def:
            errors.append(f"Unknown rule_type '{policy.rule_type}'.")
            return False, errors

        # Category check
        if policy.category not in rule_def.category_support:
            errors.append(f"Rule '{policy.rule_type}' does not support category '{policy.category}'. Allowed: {rule_def.category_support}.")

        # Scope check
        if policy.scope not in rule_def.scope_support:
            errors.append(f"Rule '{policy.rule_type}' does not support scope '{policy.scope}'. Allowed: {rule_def.scope_support}.")

        # Weight check: HARD cannot have weight; SOFT/PREFERENCE must have positive weight
        if policy.category == PolicyCategory.HARD and policy.weight is not None:
            errors.append(f"HARD constraint '{policy.name}' cannot have a weight assigned.")
        if policy.category in (PolicyCategory.SOFT, PolicyCategory.PREFERENCE):
            if policy.weight is not None and policy.weight <= 0:
                errors.append(f"Policy '{policy.name}' has non-positive weight ({policy.weight}). Weight must be > 0.")

        # Ensure default parameters from rule definition for preferences if missing
        if policy.rule_type in ("PREF_LATE_START", "PREF_ADDITIONAL_BREAK", "PREF_EARLY_FINISH"):
            for def_k, def_v in rule_def.default_parameters.items():
                if def_k not in policy.parameters:
                    policy.parameters[def_k] = copy.deepcopy(def_v)

        # Parameter schema check
        for param_name, expected_type in rule_def.parameter_schema.items():
            if param_name not in policy.parameters:
                errors.append(f"Missing required parameter '{param_name}' for rule '{policy.rule_type}'.")
            else:
                val = policy.parameters[param_name]
                if isinstance(expected_type, tuple):
                    if not any(isinstance(val, t) for t in expected_type):
                        errors.append(f"Parameter '{param_name}' must be of type {expected_type}, got {type(val).__name__}.")
                elif expected_type == list and not isinstance(val, list):
                    errors.append(f"Parameter '{param_name}' must be a list, got {type(val).__name__}.")
                elif expected_type in (int, float, str, bool) and not isinstance(val, expected_type):
                    errors.append(f"Parameter '{param_name}' must be of type {expected_type.__name__}, got {type(val).__name__}.")

        return len(errors) == 0, errors

    def validate_policy_set(self, policies: List[PolicyModel]) -> PolicyValidationResult:
        errors = []
        warnings = []
        affected_rules = []
        affected_entities = set()

        enabled_policies = [p for p in policies if p.enabled and p.status != PolicyStatus.ARCHIVED]

        # 1. Individual rule schema & category checks
        for p in enabled_policies:
            valid, p_errs = self.validate_policy(p)
            if not valid:
                for pe in p_errs:
                    errors.append({"policy_id": p.policy_id, "rule_type": p.rule_type, "message": pe})
                affected_rules.append(p.rule_type)

            for t in p.target_ids:
                affected_entities.add(f"{p.scope}:{t}")

        # 2. Contradiction: Max Daily Hours < Min Daily Hours
        sec_max = next((p for p in enabled_policies if p.rule_type == "MAX_DAILY_HOURS_SECTION"), None)
        sec_min = next((p for p in enabled_policies if p.rule_type == "MIN_DAILY_HOURS_SECTION"), None)
        if sec_max and sec_min:
            max_h = sec_max.parameters.get("max_hours", 0)
            min_h = sec_min.parameters.get("min_hours", 0)
            if min_h > max_h:
                errors.append({
                    "category": "CONTRADICTORY_DAILY_HOURS",
                    "message": f"Contradictory daily section hours: Min ({min_h}h) exceeds Max ({max_h}h).",
                    "affected_policies": [sec_max.policy_id, sec_min.policy_id]
                })
                affected_rules.extend(["MAX_DAILY_HOURS_SECTION", "MIN_DAILY_HOURS_SECTION"])

        fac_max = next((p for p in enabled_policies if p.rule_type == "MAX_DAILY_HOURS_FACULTY"), None)
        fac_min = next((p for p in enabled_policies if p.rule_type == "MIN_DAILY_HOURS_FACULTY"), None)
        if fac_max and fac_min:
            max_h = fac_max.parameters.get("max_hours", 0)
            min_h = fac_min.parameters.get("min_hours", 0)
            if min_h > max_h:
                errors.append({
                    "category": "CONTRADICTORY_DAILY_HOURS",
                    "message": f"Contradictory daily faculty hours: Min ({min_h}h) exceeds Max ({max_h}h).",
                    "affected_policies": [fac_max.policy_id, fac_min.policy_id]
                })
                affected_rules.extend(["MAX_DAILY_HOURS_FACULTY", "MIN_DAILY_HOURS_FACULTY"])

        # 3. Contradiction: Working Hours Impossible Range
        wh = next((p for p in enabled_policies if p.rule_type == "WORKING_HOURS"), None)
        if wh:
            s_start = wh.parameters.get("allowed_start_slot", 0)
            s_end = wh.parameters.get("allowed_end_slot", 8)
            if s_start >= s_end or s_start < 0 or s_end > 8:
                errors.append({
                    "category": "IMPOSSIBLE_WORKING_HOURS",
                    "message": f"Invalid working hours range: Start Slot {s_start} must be < End Slot {s_end} within [0, 8].",
                    "policy_id": wh.policy_id
                })
                affected_rules.append("WORKING_HOURS")

        # 4. Contradiction: Lunch Window outside Working Hours
        lw = next((p for p in enabled_policies if p.rule_type == "LUNCH_WINDOW"), None)
        if wh and lw:
            s_start = wh.parameters.get("allowed_start_slot", 0)
            s_end = wh.parameters.get("allowed_end_slot", 8)
            l_start = lw.parameters.get("start_slot", 3)
            l_end = lw.parameters.get("end_slot", 5)
            if l_start < s_start or l_end > (s_end + 1):
                errors.append({
                    "category": "IMPOSSIBLE_LUNCH_WINDOW",
                    "message": f"Lunch window [{l_start}, {l_end}] extends outside working hours [{s_start}, {s_end}].",
                    "policy_id": lw.policy_id
                })
                affected_rules.append("LUNCH_WINDOW")

        # 5. Warning: Closed Slot marked as Preferred Slot
        cc = next((p for p in enabled_policies if p.rule_type == "CALENDAR_CLOSURE"), None)
        ps = next((p for p in enabled_policies if p.rule_type == "PREFERRED_SLOTS"), None)
        if cc and ps:
            closed_slots = set(cc.parameters.get("slots", []))
            pref_slots = set(ps.parameters.get("slots", []))
            overlap = closed_slots.intersection(pref_slots)
            if overlap:
                warnings.append({
                    "category": "CONFLICTING_PREFERENCE_ON_CLOSED_SLOT",
                    "message": f"Slots {list(overlap)} are closed by Calendar Closure but marked as Preferred Slots.",
                    "slots": list(overlap)
                })

        # 6. Warning: Room Forbidden and Preferred for same target
        fr = next((p for p in enabled_policies if p.rule_type == "FORBIDDEN_ROOMS"), None)
        pr = next((p for p in enabled_policies if p.rule_type == "PREFERRED_ROOMS"), None)
        if fr and pr:
            f_rooms = set(fr.parameters.get("room_ids", []))
            p_rooms = set(pr.parameters.get("room_ids", []))
            overlap = f_rooms.intersection(p_rooms)
            if overlap:
                warnings.append({
                    "category": "ROOM_FORBIDDEN_AND_PREFERRED",
                    "message": f"Rooms {list(overlap)} are listed in both Forbidden and Preferred Room policies.",
                    "rooms": list(overlap)
                })

        # 7. Precedence Check: Hard vs Soft/Preference Conflict
        # Hard constraint always overrides Soft/Preference. If a hard rule and soft rule apply to same target,
        # it is a valid policy set with priority guarantee.

        # 8. Optimization Preference Contradiction Checks
        late_starts = [p for p in enabled_policies if p.rule_type == "PREF_LATE_START"]
        early_finishes = [p for p in enabled_policies if p.rule_type == "PREF_EARLY_FINISH"]
        for ls in late_starts:
            s_slot = ls.parameters.get("preferred_start_slot", 1)
            if not isinstance(s_slot, int) or s_slot < 0 or s_slot > 8:
                errors.append({
                    "category": "INVALID_PREFERENCE_SLOT",
                    "message": f"Preferred Start Slot {s_slot} must be an integer within operational slots [0, 8].",
                    "policy_id": ls.policy_id
                })
                affected_rules.append("PREF_LATE_START")
            for ef in early_finishes:
                if ls.scope == ef.scope:
                    f_slot = ef.parameters.get("preferred_finish_slot", 7)
                    if isinstance(s_slot, int) and isinstance(f_slot, int) and s_slot >= f_slot:
                        errors.append({
                            "category": "CONTRADICTORY_PREFERENCE_SLOTS",
                            "message": f"Contradictory scheduling preference: Preferred Start Slot ({s_slot}) must be earlier than Preferred Finish Slot ({f_slot}).",
                            "affected_policies": [ls.policy_id, ef.policy_id]
                        })
                        affected_rules.extend(["PREF_LATE_START", "PREF_EARLY_FINISH"])

        for ef in early_finishes:
            f_slot = ef.parameters.get("preferred_finish_slot", 7)
            if not isinstance(f_slot, int) or f_slot < 0 or f_slot > 8:
                errors.append({
                    "category": "INVALID_PREFERENCE_SLOT",
                    "message": f"Preferred Finish Slot {f_slot} must be an integer within operational slots [0, 8].",
                    "policy_id": ef.policy_id
                })
                affected_rules.append("PREF_EARLY_FINISH")

        add_breaks = [p for p in enabled_policies if p.rule_type == "PREF_ADDITIONAL_BREAK"]
        for ab in add_breaks:
            tot_free = ab.parameters.get("preferred_total_free_hours", 2)
            if not isinstance(tot_free, (int, float)) or tot_free <= 0:
                errors.append({
                    "category": "INVALID_BREAK_HOURS",
                    "message": f"Preferred total free hours must be greater than 0, got {tot_free}.",
                    "policy_id": ab.policy_id
                })
                affected_rules.append("PREF_ADDITIONAL_BREAK")

        return PolicyValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            affected_rules=sorted(list(set(affected_rules))),
            affected_entities=sorted(list(affected_entities)),
            estimated_schedule_impact={"hard_error_count": len(errors), "warning_count": len(warnings)}
        )

# ------------------------------------------------------------------------------
# Policy Impact Analyzer (Non-Optimizing Feasibility Preview)
# ------------------------------------------------------------------------------

class PolicyImpactAnalyzer:
    """
    Evaluates a proposed policy configuration against current timetable events
    WITHOUT running solvers, optimization, or timetable mutation.
    """
    def __init__(self, validator: Optional[PolicyValidator] = None):
        self.validator = validator or PolicyValidator()

    def analyze_impact(self, events: List[Dict[str, Any]], policies: List[PolicyModel]) -> Dict[str, Any]:
        hard_violations = []
        soft_violations = []
        affected_sections = set()
        affected_faculty = set()
        affected_rooms = set()
        affected_event_ids = set()

        enabled_policies = [p for p in policies if p.enabled and p.status != PolicyStatus.ARCHIVED]

        # 1. Calendar Closure (e.g. Friday post-lunch)
        closures = [p for p in enabled_policies if p.rule_type == "CALENDAR_CLOSURE"]
        for c in closures:
            c_days = c.parameters.get("days", [])
            c_slots = set(c.parameters.get("slots", []))
            for ev in events:
                if ev.get("day_idx") in c_days:
                    ev_slots = set(range(ev.get("start_slot", 0), ev.get("start_slot", 0) + ev.get("duration", 1)))
                    if ev_slots.intersection(c_slots):
                        hard_violations.append({
                            "policy_id": c.policy_id,
                            "event_id": ev.get("event_id"),
                            "subject": ev.get("subject"),
                            "message": f"Event #{ev.get('event_id')} scheduled in closed slot on {ev.get('day_name')}."
                        })
                        affected_event_ids.add(ev.get("event_id"))
                        for s in ev.get("sections", []): affected_sections.add(s)
                        for f in ev.get("faculty", []): affected_faculty.add(f)
                        if ev.get("room") != "NO_ROOM": affected_rooms.add(ev.get("room"))

        # 2. Max Consecutive Hours Section (Soft violation)
        max_consec_p = next((p for p in enabled_policies if p.rule_type == "MAX_CONSECUTIVE_HOURS_SECTION"), None)
        if max_consec_p:
            max_c = max_consec_p.parameters.get("max_hours", 3)
            # Find consecutive runs per section per day
            sec_runs = {}
            for ev in events:
                day = ev.get("day_idx")
                for s in ev.get("sections", []):
                    key = (s, day)
                    if key not in sec_runs: sec_runs[key] = []
                    for sl in range(ev.get("start_slot", 0), ev.get("start_slot", 0) + ev.get("duration", 1)):
                        sec_runs[key].append((sl, ev.get("event_id")))

            for (sec, day), slots_events in sec_runs.items():
                slots_events.sort(key=lambda x: x[0])
                cur_run = 1
                for i in range(1, len(slots_events)):
                    if slots_events[i][0] == slots_events[i-1][0] + 1:
                        cur_run += 1
                        if cur_run > max_c:
                            soft_violations.append({
                                "policy_id": max_consec_p.policy_id,
                                "section": sec,
                                "day": day,
                                "message": f"Section {sec} exceeds {max_c} consecutive hours on Day {day}."
                            })
                            affected_sections.add(sec)
                            affected_event_ids.add(slots_events[i][1])
                    else:
                        cur_run = 1

        return {
            "total_events_checked": len(events),
            "new_hard_violations_count": len(hard_violations),
            "new_soft_violations_count": len(soft_violations),
            "hard_violations": hard_violations,
            "soft_violations": soft_violations,
            "affected_sections": sorted(list(affected_sections)),
            "affected_faculty": sorted(list(affected_faculty)),
            "affected_rooms": sorted(list(affected_rooms)),
            "affected_events_count": len(affected_event_ids),
            "affected_event_ids": sorted(list(affected_event_ids))
        }

# ------------------------------------------------------------------------------
# Policy Repository, Versioning & RBAC Management
# ------------------------------------------------------------------------------

class PolicyService:
    """
    Transactional policy builder repository managing version immutability,
    draft editing, template instantiation, and audit logging.
    """
    def __init__(self, auth_svc: auth_service.AuthenticationService):
        self.auth = auth_svc
        self.registry = GLOBAL_RULE_REGISTRY
        self.validator = PolicyValidator(self.registry)
        self.analyzer = PolicyImpactAnalyzer(self.validator)
        # project_id -> {
        #   "active_version": str,
        #   "versions": Dict[version_id, { "version_id": str, "policies": List[PolicyModel], "created_at": str, "created_by": str, "status": str }],
        #   "draft_policies": List[PolicyModel],
        #   "audit_log": List[Dict[str, Any]]
        # }
        self.project_policies: Dict[str, Dict[str, Any]] = {}

    def initialize_project_policies(self, user: User, project_id: str, template_id: str = "WOXSEN_CERTIFIED_PROFILE") -> Tuple[bool, str]:
        if template_id == "WOXSEN_CERTIFIED_PROFILE":
            pols = get_woxsen_certified_profile(project_id)
        else:
            pols = get_default_university_policies(project_id)

        v1_id = f"polver_{uuid.uuid4().hex[:8]}"
        for p in pols:
            p.policy_version_id = v1_id
            p.created_by_user_id = user.user_id

        self.project_policies[project_id] = {
            "active_version": v1_id,
            "versions": {
                v1_id: {
                    "version_id": v1_id,
                    "version_number": 1,
                    "policies": copy.deepcopy(pols),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": user.user_id,
                    "status": PolicyStatus.ACTIVE,
                    "summary": f"Initialized from template {template_id}"
                }
            },
            "draft_policies": copy.deepcopy(pols),
            "audit_log": []
        }

        self.auth.audit.log_event(
            AuditEventType.PROJECT_UPDATED,
            user_id=user.user_id,
            project_id=project_id,
            metadata={"action": "POLICY_TEMPLATE_APPLIED", "template_id": template_id, "version_id": v1_id}
        )
        return True, f"Policies initialized for project {project_id}."

    def get_active_policies(self, project_id: str) -> List[PolicyModel]:
        if project_id not in self.project_policies:
            return []
        p_data = self.project_policies[project_id]
        v_id = p_data.get("active_version")
        if v_id and v_id in p_data["versions"]:
            return p_data["versions"][v_id]["policies"]
        return []

    def get_draft_policies(self, project_id: str) -> List[PolicyModel]:
        if project_id not in self.project_policies:
            return []
        return self.project_policies[project_id].get("draft_policies", [])

    def create_policy(self, user: User, project_id: str, policy: PolicyModel) -> Tuple[bool, Optional[PolicyModel], str]:
        # RBAC Check: Super Admin & Timetable Admin only
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            self.auth.audit.log_event(AuditEventType.ACCESS_DENIED, user_id=user.user_id, project_id=project_id, metadata={"action": "CREATE_POLICY"})
            return False, None, "Permission Denied: Only Timetable Administrators can create policies."

        if project_id not in self.project_policies:
            self.initialize_project_policies(user, project_id)

        # Validate policy schema
        valid, errs = self.validator.validate_policy(policy)
        if not valid:
            return False, None, f"Policy validation failed: {'; '.join(errs)}"

        policy.created_by_user_id = user.user_id
        policy.status = PolicyStatus.DRAFT
        self.project_policies[project_id]["draft_policies"].append(policy)

        self.auth.audit.log_event(
            AuditEventType.PROJECT_UPDATED,
            user_id=user.user_id,
            project_id=project_id,
            metadata={"action": "POLICY_CREATED", "policy_id": policy.policy_id, "rule_type": policy.rule_type}
        )
        return True, policy, "Policy created as DRAFT."

    def duplicate_policy(self, user: User, project_id: str, policy_id: str) -> Tuple[bool, Optional[PolicyModel], str]:
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            return False, None, "Permission Denied: Administrators only."

        drafts = self.project_policies[project_id]["draft_policies"]
        target = next((p for p in drafts if p.policy_id == policy_id), None)
        if not target:
            return False, None, "Policy not found."

        new_pol = copy.deepcopy(target)
        new_pol.policy_id = f"pol_{uuid.uuid4().hex[:8]}"
        new_pol.name = f"{target.name} (Copy)"
        new_pol.status = PolicyStatus.DRAFT
        new_pol.created_at = datetime.now(timezone.utc).isoformat()
        drafts.append(new_pol)
        return True, new_pol, "Policy duplicated successfully."

    def toggle_policy_enabled(self, user: User, project_id: str, policy_id: str, enabled: bool) -> Tuple[bool, str]:
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            return False, "Permission Denied: Administrators only."

        drafts = self.project_policies[project_id]["draft_policies"]
        target = next((p for p in drafts if p.policy_id == policy_id), None)
        if not target:
            return False, "Policy not found."

        target.enabled = enabled
        target.updated_at = datetime.now(timezone.utc).isoformat()
        action = "POLICY_ENABLED" if enabled else "POLICY_DISABLED"
        self.auth.audit.log_event(
            AuditEventType.PROJECT_UPDATED,
            user_id=user.user_id,
            project_id=project_id,
            metadata={"action": action, "policy_id": policy_id}
        )
        return True, f"Policy {policy_id} {'enabled' if enabled else 'disabled'}."

    def archive_policy(self, user: User, project_id: str, policy_id: str) -> Tuple[bool, str]:
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            return False, "Permission Denied: Administrators only."

        drafts = self.project_policies[project_id]["draft_policies"]
        target = next((p for p in drafts if p.policy_id == policy_id), None)
        if not target:
            return False, "Policy not found."

        target.status = PolicyStatus.ARCHIVED
        target.enabled = False
        target.updated_at = datetime.now(timezone.utc).isoformat()
        self.auth.audit.log_event(
            AuditEventType.PROJECT_UPDATED,
            user_id=user.user_id,
            project_id=project_id,
            metadata={"action": "POLICY_ARCHIVED", "policy_id": policy_id}
        )
        return True, f"Policy {policy_id} archived."

    def activate_policy_version(self, user: User, project_id: str, summary: str = "") -> Tuple[bool, Optional[str], str]:
        """
        Validates draft policies and creates a new immutable active version.
        Rejects activation if contradictory hard errors exist.
        """
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            return False, None, "Permission Denied: Administrators only."

        p_data = self.project_policies[project_id]
        drafts = p_data["draft_policies"]

        # Run complete pre-activation validation
        val_res = self.validator.validate_policy_set(drafts)
        if not val_res.valid:
            self.auth.audit.log_event(
                AuditEventType.PROJECT_UPDATED,
                user_id=user.user_id,
                project_id=project_id,
                metadata={"action": "POLICY_VALIDATION_FAILED", "errors": val_res.errors}
            )
            return False, None, f"Cannot activate: {len(val_res.errors)} validation errors detected."

        # Create immutable version record
        v_num = len(p_data["versions"]) + 1
        new_v_id = f"polver_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        activated_pols = []
        for d in drafts:
            cp = copy.deepcopy(d)
            cp.policy_version_id = new_v_id
            cp.status = PolicyStatus.ACTIVE if cp.status != PolicyStatus.ARCHIVED else PolicyStatus.ARCHIVED
            activated_pols.append(cp)

        p_data["versions"][new_v_id] = {
            "version_id": new_v_id,
            "version_number": v_num,
            "policies": activated_pols,
            "created_at": now,
            "created_by": user.user_id,
            "status": PolicyStatus.ACTIVE,
            "summary": summary or f"Activated policy version v{v_num}"
        }
        p_data["active_version"] = new_v_id
        p_data["draft_policies"] = copy.deepcopy(activated_pols)

        self.auth.audit.log_event(
            AuditEventType.VERSION_CREATED,
            user_id=user.user_id,
            project_id=project_id,
            version_id=new_v_id,
            metadata={"action": "POLICY_ACTIVATED", "version_number": v_num, "rule_count": len(activated_pols)}
        )
        return True, new_v_id, f"Policy version {new_v_id} (v{v_num}) activated successfully."

    def rollback_policy_version(self, user: User, project_id: str, target_version_id: str) -> Tuple[bool, Optional[str], str]:
        """
        Creates a NEW policy version based on a historical version snapshot (history is append-only).
        """
        if user.role not in (UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN):
            return False, None, "Permission Denied: Administrators only."

        p_data = self.project_policies[project_id]
        if target_version_id not in p_data["versions"]:
            return False, None, "Target historical version not found."

        hist_pols = p_data["versions"][target_version_id]["policies"]
        p_data["draft_policies"] = copy.deepcopy(hist_pols)
        return self.activate_policy_version(user, project_id, summary=f"Rollback to configuration of {target_version_id}")
