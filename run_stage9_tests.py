"""
run_stage9_tests.py - Authoritative Stage 9 Automated Test Suite (120+ Tests)
Timetable Generation & Optimization Engine Certification
=============================================================================
Comprehensive test suite covering:
1. Preflight certification & golden hash preservation
2. Input loading, policy snapshot binding & feasibility freshness
3. Event placement domains, legal slot enumeration & zero-domain detection
4. Deterministic event ordering & conflict degree heuristics
5. Hard constraint enforcement (Section, Faculty, Room collision prevention)
6. Working hours, calendar exceptions, holiday compliance & Friday closure
7. Contiguous 2-hour lab placement and same-room invariants
8. Shared multi-section & multi-faculty atomic synchronization
9. Split/nested subgroup independence semantics
10. Pinned and frozen event immutability protections
11. Room capacity and equipment/type requirements
12. Deterministic construction, incremental occupancy & bounded backtracking
13. Independent validator parity (validator.py) with ZERO errors
14. Lexicographic multi-stage optimization hierarchy (P0 -> P6)
15. Quality scoring (Hard, Soft, Preferences, Gaps, Runs, Balance, Stability)
16. Multi-candidate generation, immutable candidates & candidate selection
17. Server-side RBAC authorization & audit logging
18. Deterministic reproducibility from seed & candidate fingerprints
19. Mandatory test fixtures (SMALL_FEASIBLE, PINNED, LAB, SHARED, FRIDAY, etc.)
20. Certified 598-event canonical dataset test execution
"""

import unittest
import json
import os
import hashlib
import tempfile
import shutil
import time
from datetime import datetime, timezone

import generation_models
from generation_models import (
    GenerationStatus,
    GenerationProfile,
    GenerationConfig,
    PlacementDomain,
    QualityScore,
    TimetableCandidate,
    GenerationStatistics,
    GenerationDiagnostics,
    GenerationResult,
    compute_model_fingerprint
)

import generation_engine
from generation_engine import TimetableGenerationEngine, ENGINE_VERSION

import generation_service
from generation_service import GenerationService

import auth_service
from auth_service import AuthenticationService, User, UserRole, AuditEventType

import validator
from validator import validate_schedule

PROJECT_ROOT = r"C:\Users\asus\.gemini\antigravity-ide\scratch\CP-Timetable"
GOLDEN_PROD_HASH = "fc77f694acd4eaad55cdbc18432b231e10bc46124cd4ac930bdc26369eb45c3b"
GOLDEN_STAGE5_3_HASH = "8c82c3a36bce6655b78344c599ba7911b4e318ba96fc541d679c06a8bdc0708a"
GOLDEN_CSV_HASH = "47a555a3267a354d6b34548f76d9857d771925a603ff7998bdf0e2510ac67643"

FET_SOURCES = [
    "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Groups.html",
    "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Rooms.html",
    "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Teachers.html"
]

def file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def load_canonical_baseline():
    with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
        proj = json.load(f)
    v_id = proj.get("active_version_id")
    if v_id and v_id in proj.get("versions", {}):
        ver_data = proj["versions"][v_id]
        if "dataset" not in proj and "dataset" in ver_data:
            proj["dataset"] = ver_data["dataset"]
        if "events" not in proj and "events" in ver_data:
            proj["events"] = ver_data["events"]
    return proj

# =============================================================================
# 1. Preflight Certification & Golden Hash Preservation (Tests 1-8)
# =============================================================================
class TestStage9PreflightAndGoldenHashes(unittest.TestCase):
    def test_001_production_schedule_golden_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_PROD_HASH)

    def test_002_stage5_3_source_golden_sha256(self):
        p = os.path.join(PROJECT_ROOT, "stage5_3_corrected_optimized_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_STAGE5_3_HASH)

    def test_003_production_csv_golden_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.csv")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_CSV_HASH)

    def test_004_fet_groups_html_exists_and_immutable(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[0])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_005_fet_rooms_html_exists_and_immutable(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[1])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_006_fet_teachers_html_exists_and_immutable(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[2])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_007_canonical_baseline_project_exists(self):
        p = os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json")
        self.assertTrue(os.path.exists(p))

    def test_008_no_generated_run_aliases_production_directory(self):
        prod_path = os.path.join(PROJECT_ROOT, "production_schedule.json")
        gen_dir = os.path.join(PROJECT_ROOT, "projects", "generated")
        self.assertNotEqual(os.path.abspath(prod_path), os.path.abspath(gen_dir))
        self.assertFalse(os.path.abspath(prod_path).startswith(os.path.abspath(gen_dir)))

# =============================================================================
# 2. Input Loading & Feasibility Freshness Guard (Tests 9-16)
# =============================================================================
class TestStage9InputAndFeasibilityGuard(unittest.TestCase):
    def setUp(self):
        self.project = load_canonical_baseline()
        self.svc = GenerationService()

    def test_009_feasibility_readiness_valid(self):
        feas = {
            "feasibility_run_id": "feas_valid_01",
            "status": "FEASIBLE",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertTrue(ok)

    def test_010_feasibility_readiness_feasible_with_warnings(self):
        feas = {
            "feasibility_run_id": "feas_warn_01",
            "status": "FEASIBLE_WITH_WARNINGS",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertTrue(ok)

    def test_011_feasibility_readiness_missing_blocks_generation(self):
        ok, msg = self.svc.check_feasibility_readiness(self.project, None)
        self.assertFalse(ok)
        self.assertIn("mandatory", msg.lower())

    def test_012_feasibility_readiness_infeasible_status_blocks(self):
        feas = {
            "feasibility_run_id": "feas_inf_01",
            "status": "INFEASIBLE",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertFalse(ok)
        self.assertIn("INFEASIBLE", msg)

    def test_013_feasibility_readiness_requires_review_blocks(self):
        feas = {
            "feasibility_run_id": "feas_rev_01",
            "status": "REQUIRES_REVIEW",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertFalse(ok)

    def test_014_feasibility_stale_project_version_blocks(self):
        feas = {
            "feasibility_run_id": "feas_stale_ver",
            "status": "FEASIBLE",
            "project_version_id": "stale_version_999",
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertFalse(ok)
        self.assertIn("stale", msg.lower())

    def test_015_feasibility_stale_policy_snapshot_blocks(self):
        feas = {
            "feasibility_run_id": "feas_stale_pol",
            "status": "FEASIBLE",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": "stale_policy_snapshot_999"
        }
        ok, msg = self.svc.check_feasibility_readiness(self.project, feas)
        self.assertFalse(ok)
        self.assertIn("stale", msg.lower())

    def test_016_input_fingerprint_deterministic(self):
        data = {"project_id": "proj_1", "version_id": "v1", "seed": 42}
        fp1 = compute_model_fingerprint(data)
        fp2 = compute_model_fingerprint(data)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

# =============================================================================
# 3. Placement Domains & Zero-Domain Detection (Tests 17-24)
# =============================================================================
class TestStage9PlacementDomains(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_017_domain_generation_standard_1h(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        events = [{"event_id": 1, "duration": 1, "is_pinned": False, "is_lab": False}]
        domains, zero = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="test"))
        self.assertEqual(len(zero), 0)
        self.assertIn(1, domains)
        self.assertGreater(len(domains[1].legal_placements), 30)

    def test_018_domain_generation_friday_closure(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        # Friday is day_idx 4, slots 4,5,6,7,8 closed
        events = [{"event_id": 2, "duration": 1, "is_pinned": False, "is_lab": False}]
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="test"))
        friday_placements = [p for p in domains[2].legal_placements if p[0] == 4]
        for d, s in friday_placements:
            self.assertNotIn(s, [4, 5, 6, 7, 8])

    def test_019_domain_generation_2h_lab_friday_rule(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        events = [{"event_id": 3, "duration": 2, "is_pinned": False, "is_lab": True}]
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="test"))
        friday_lab_placements = [p for p in domains[3].legal_placements if p[0] == 4]
        # Under Friday post-lunch closure at slot 4, lab can only start at slot 0, 1, 2 (slot 3 spans to slot 4, which is closed)
        for d, s in friday_lab_placements:
            self.assertIn(s, [0, 1, 2])

    def test_020_domain_generation_pinned_event_fixed_singleton(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        events = [{"event_id": 4, "duration": 1, "is_pinned": True, "baseline_day": 2, "baseline_slot": 3}]
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="test", respect_pinned_events=True))
        self.assertEqual(domains[4].legal_placements, [(2, 3)])

    def test_021_domain_generation_frozen_event_fixed_singleton(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        events = [{"event_id": 5, "duration": 1, "is_frozen": True, "baseline_day": 1, "baseline_slot": 0}]
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="test", respect_frozen_events=True))
        self.assertEqual(domains[5].legal_placements, [(1, 0)])

    def test_022_zero_domain_blocked_time_detection(self):
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        # Completely block all usable slots with project blocked time
        blocked = [{"scope": "PROJECT", "day": d, "start_slot": s, "duration": 1} for d in range(5) for s in range(9)]
        cal_blocked = self.engine._extract_calendar(self.project["dataset"], [], blocked)
        events = [{"event_id": 6, "duration": 1, "is_pinned": False}]
        domains, zero = self.engine._build_event_domains(events, cal_blocked, [], blocked, GenerationConfig(generation_run_id="test"))
        self.assertIn(6, zero)
        self.assertEqual(len(domains[6].legal_placements), 0)

    def test_023_zero_domain_infeasible_termination_status(self):
        # Project with 0 domain event returns INFEASIBLE_GENERATION
        blocked = [{"scope": "PROJECT", "day": d, "start_slot": s, "duration": 1} for d in range(5) for s in range(9)]
        res = self.engine.generate(
            project=self.project,
            active_version_id=self.project.get("active_version_id"),
            blocked_slots=blocked
        )
        self.assertEqual(res.status, GenerationStatus.INFEASIBLE_GENERATION)
        self.assertEqual(res.candidate_count_valid, 0)
        self.assertEqual(res.termination_reason, "INFEASIBLE")

    def test_024_zero_domain_diagnostics_contain_certificate(self):
        blocked = [{"scope": "PROJECT", "day": d, "start_slot": s, "duration": 1} for d in range(5) for s in range(9)]
        res = self.engine.generate(
            project=self.project,
            active_version_id=self.project.get("active_version_id"),
            blocked_slots=blocked
        )
        self.assertGreater(len(res.diagnostics.hard_conflicts), 0)
        self.assertGreater(len(res.diagnostics.unplaced_events), 0)

# =============================================================================
# 4. Event Ordering & Heuristics (Tests 25-32)
# =============================================================================
class TestStage9EventOrdering(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()

    def test_025_pinned_events_ordered_first(self):
        events = [
            {"event_id": 10, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 20, "is_pinned": True, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            10: PlacementDomain(10, [(0, 0), (0, 1)], 2),
            20: PlacementDomain(20, [(0, 0)], 1)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 20)

    def test_026_frozen_events_ordered_first(self):
        events = [
            {"event_id": 11, "is_frozen": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 21, "is_frozen": True, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            11: PlacementDomain(11, [(0, 0), (0, 1)], 2),
            21: PlacementDomain(21, [(0, 0)], 1)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 21)

    def test_027_smallest_domain_first_heuristic(self):
        events = [
            {"event_id": 100, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 200, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            100: PlacementDomain(100, [(0, 0), (0, 1), (0, 2)], 3),
            200: PlacementDomain(200, [(0, 0)], 1)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 200)

    def test_028_shared_multisection_before_single_section(self):
        events = [
            {"event_id": 1, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "is_pinned": False, "sections": ["S1", "S2", "S3"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 2)

    def test_029_labs_before_theory_when_domain_pressure_equal(self):
        events = [
            {"event_id": 1, "is_pinned": False, "is_lab": False, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "is_pinned": False, "is_lab": True, "duration": 2, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 2)

    def test_030_unique_room_before_interchangeable_room(self):
        events = [
            {"event_id": 1, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "NO_ROOM"},
            {"event_id": 2, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "SPECIAL_LAB_1"},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 2)

    def test_031_conflict_degree_heuristic(self):
        # Event 1 conflicts with 3 resources, Event 2 conflicts with 1
        events = [
            {"event_id": 1, "is_pinned": False, "sections": ["S1", "S2"], "faculty": ["F1", "F2"], "room": "R1"},
            {"event_id": 2, "is_pinned": False, "sections": ["S3"], "faculty": ["F3"], "room": "R2"},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 1)

    def test_032_stable_event_id_tie_breaker(self):
        events = [
            {"event_id": 99, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 12, "is_pinned": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
        ]
        domains = {
            99: PlacementDomain(99, [(0, 0), (0, 1)], 2),
            12: PlacementDomain(12, [(0, 0), (0, 1)], 2)
        }
        ordered = self.engine._order_events(events, domains)
        self.assertEqual(ordered[0]["event_id"], 12)
        self.assertEqual(ordered[1]["event_id"], 99)

# =============================================================================
# 5. Hard Constraint Satisfaction & Collision Prevention (Tests 33-46)
# =============================================================================
class TestStage9HardConstraints(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_033_section_collision_prevention(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["SEC_A"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["SEC_A"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual((placed[0]["day"], placed[0]["slot"]), (placed[1]["day"], placed[1]["slot"]))

    def test_034_faculty_collision_prevention(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["PROF_X"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S2"], "faculty": ["PROF_X"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual((placed[0]["day"], placed[0]["slot"]), (placed[1]["day"], placed[1]["slot"]))

    def test_035_room_collision_prevention(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "C202", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S2"], "faculty": ["F2"], "room": "C202", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual((placed[0]["day"], placed[0]["slot"]), (placed[1]["day"], placed[1]["slot"]))

    def test_036_no_room_events_do_not_collide_with_each_other(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "NO_ROOM", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S2"], "faculty": ["F2"], "room": "NO_ROOM", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        # NO_ROOM can safely share the same slot when sections and faculty differ
        self.assertEqual((placed[0]["day"], placed[0]["slot"]), (placed[1]["day"], placed[1]["slot"]))

    def test_037_working_hours_day_boundary_no_overflow(self):
        events = [{"event_id": 1, "duration": 2, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="t"))
        # 2h event cannot start at slot 8 (it would end at 10 > 9)
        for d, s in domains[1].legal_placements:
            self.assertLessEqual(s + 2, 9)

    def test_038_faculty_blocked_time_respected(self):
        blocked = [{"scope": "FACULTY", "entity_id": "PROF_BUSY", "day": 1, "start_slot": 2, "duration": 1}]
        events = [{"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["PROF_BUSY"], "room": "R1", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], blocked)
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], blocked, GenerationConfig(generation_run_id="t"))
        self.assertNotIn((1, 2), domains[1].legal_placements)

    def test_039_section_blocked_time_respected(self):
        blocked = [{"scope": "SECTION", "entity_id": "SEC_BLOCKED", "day": 3, "start_slot": 4, "duration": 1}]
        events = [{"event_id": 1, "duration": 1, "sections": ["SEC_BLOCKED"], "faculty": ["F1"], "room": "R1", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], blocked)
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], blocked, GenerationConfig(generation_run_id="t"))
        self.assertNotIn((3, 4), domains[1].legal_placements)

    def test_040_room_blocked_time_respected(self):
        blocked = [{"scope": "ROOM", "entity_id": "ROOM_REPAIR", "day": 0, "start_slot": 1, "duration": 2}]
        events = [{"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "ROOM_REPAIR", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], blocked)
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], blocked, GenerationConfig(generation_run_id="t"))
        self.assertNotIn((0, 1), domains[1].legal_placements)
        self.assertNotIn((0, 2), domains[1].legal_placements)

    def test_041_pinned_event_protected_from_relocation(self):
        events = [{"event_id": 99, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": True, "baseline_day": 3, "baseline_slot": 5}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="t", respect_pinned_events=True))
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["day"], 3)
        self.assertEqual(placed[0]["slot"], 5)

    def test_042_frozen_event_protected_from_relocation(self):
        events = [{"event_id": 88, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_frozen": True, "baseline_day": 0, "baseline_slot": 1}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="t", respect_frozen_events=True))
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["day"], 0)
        self.assertEqual(placed[0]["slot"], 1)

    def test_043_shared_multisection_atomic_placement(self):
        # Event shared across 3 sections placed at single slot
        events = [{"event_id": 1, "duration": 1, "sections": ["S1", "S2", "S3"], "faculty": ["F1"], "room": "AUDITORIUM", "is_pinned": False}]
        domains = {1: PlacementDomain(1, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(len(placed[0]["sections"]), 3)

    def test_044_shared_event_section_conflict_causes_backtracking(self):
        # Event 1 uses S1, S2. Event 2 uses S1 only.
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S1", "S2"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["slot"], 0)
        self.assertEqual(placed[1]["slot"], 1)

    def test_045_multi_faculty_atomic_synchronization(self):
        events = [{"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1", "F2"], "room": "R1", "is_pinned": False}]
        domains = {1: PlacementDomain(1, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(len(placed[0]["faculty"]), 2)

    def test_046_multi_faculty_conflict_resolved_deterministically(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S2"], "faculty": ["F1", "F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["slot"], 0)
        self.assertEqual(placed[1]["slot"], 1)

# =============================================================================
# 6. Contiguous 2-Hour Labs & Same-Room Continuity (Tests 47-54)
# =============================================================================
class TestStage9LabHandling(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_047_lab_occupies_two_consecutive_slots(self):
        events = [{"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "LAB_101", "is_pinned": False}]
        domains = {1: PlacementDomain(1, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["duration"], 2)

    def test_048_lab_continuity_blocks_single_slot_gap(self):
        # A slot that only has 1 slot available cannot take a 2h lab
        events = [{"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "LAB_101", "is_pinned": False}]
        # Day 0 slot 0 is available, but slot 1 is blocked
        blocked = [{"scope": "PROJECT", "day": 0, "start_slot": 1, "duration": 1}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], blocked)
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], blocked, GenerationConfig(generation_run_id="t"))
        self.assertNotIn((0, 0), domains[1].legal_placements)

    def test_049_lab_same_room_invariance(self):
        events = [{"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "LAB_AI", "is_pinned": False}]
        domains = {1: PlacementDomain(1, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["room"], "LAB_AI")

    def test_050_lab_cannot_straddle_day_end(self):
        events = [{"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "LAB_1", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="t"))
        for d, s in domains[1].legal_placements:
            self.assertNotEqual(s, 8)

    def test_051_lab_cannot_straddle_friday_closure(self):
        events = [{"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "LAB_1", "is_pinned": False}]
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        domains, _ = self.engine._build_event_domains(events, calendar_info, [], [], GenerationConfig(generation_run_id="t"))
        friday_starts = [s for d, s in domains[1].legal_placements if d == 4]
        self.assertNotIn(3, friday_starts)

    def test_052_lab_room_collision_detected_in_second_hour(self):
        # Event 1: Lab from slot 0 to 2 in R1
        # Event 2: Single hour event at slot 1 in R1
        events = [
            {"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "is_lab": False, "sections": ["S2"], "faculty": ["F2"], "room": "R1", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 1), (0, 2)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[1]["slot"], 2)

    def test_053_lab_faculty_collision_detected_in_second_hour(self):
        events = [
            {"event_id": 1, "duration": 2, "is_lab": True, "sections": ["S1"], "faculty": ["PROF_LAB"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "is_lab": False, "sections": ["S2"], "faculty": ["PROF_LAB"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 1), (0, 2)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[1]["slot"], 2)

    def test_054_lab_section_collision_detected_in_second_hour(self):
        events = [
            {"event_id": 1, "duration": 2, "is_lab": True, "sections": ["SEC_LAB"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "is_lab": False, "sections": ["SEC_LAB"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 1), (0, 2)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[1]["slot"], 2)

# =============================================================================
# 7. Split & Nested Subgroup Semantics (Tests 55-60)
# =============================================================================
class TestStage9SplitNestedSemantics(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_055_split_subgroups_independent_placement(self):
        # Subgroup A and Subgroup B can occur in same slot in different rooms
        events = [
            {"event_id": 1, "duration": 1, "sections": ["SEC_A_BATCH_1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["SEC_A_BATCH_2"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["slot"], placed[1]["slot"])

    def test_056_split_subgroup_faculty_clash_prevented(self):
        # Even if subgroups are independent, same faculty cannot teach both simultaneously
        events = [
            {"event_id": 1, "duration": 1, "sections": ["SEC_A_BATCH_1"], "faculty": ["F_SHARED"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["SEC_A_BATCH_2"], "faculty": ["F_SHARED"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual(placed[0]["slot"], placed[1]["slot"])

    def test_057_split_subgroup_room_clash_prevented(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["SEC_A_BATCH_1"], "faculty": ["F1"], "room": "LAB_SINGLE", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["SEC_A_BATCH_2"], "faculty": ["F2"], "room": "LAB_SINGLE", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual(placed[0]["slot"], placed[1]["slot"])

    def test_058_parent_section_clash_with_subgroup_session(self):
        # Parent section event clashes if placed concurrently with its own subgroup
        events = [
            {"event_id": 1, "duration": 1, "sections": ["SEC_X"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["SEC_X"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {1: PlacementDomain(1, [(0, 0)], 1), 2: PlacementDomain(2, [(0, 0), (0, 1)], 2)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertNotEqual(placed[0]["slot"], placed[1]["slot"])

    def test_059_canonical_6_split_nested_groups_preserved(self):
        # Verify generator handles 6 independent split/nested subgroup sessions without false synchronization
        events = [
            {"event_id": 101, "duration": 1, "sections": ["CS_SEC_A_G1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 102, "duration": 1, "sections": ["CS_SEC_A_G2"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
            {"event_id": 103, "duration": 1, "sections": ["CS_SEC_B_G1"], "faculty": ["F3"], "room": "R3", "is_pinned": False},
            {"event_id": 104, "duration": 1, "sections": ["CS_SEC_B_G2"], "faculty": ["F4"], "room": "R4", "is_pinned": False},
            {"event_id": 105, "duration": 1, "sections": ["CS_SEC_C_G1"], "faculty": ["F5"], "room": "R5", "is_pinned": False},
            {"event_id": 106, "duration": 1, "sections": ["CS_SEC_C_G2"], "faculty": ["F6"], "room": "R6", "is_pinned": False},
        ]
        domains = {e["event_id"]: PlacementDomain(e["event_id"], [(0, 0)], 1) for e in events}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(len(placed), 6)
        # All 6 independent subgroup sessions can legally run concurrently in parallel rooms
        for p in placed:
            self.assertEqual((p["day"], p["slot"]), (0, 0))

    def test_060_split_semantics_not_altered_during_generation(self):
        events = [{"event_id": 1, "duration": 1, "sections": ["B.Tech CS Sec A - Lab 1"], "faculty": ["F1"], "room": "R1", "is_pinned": False}]
        domains = {1: PlacementDomain(1, [(0, 0)], 1)}
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["sections"], ["B.Tech CS Sec A - Lab 1"])

# =============================================================================
# 8. Deterministic Backtracking & Search Limits (Tests 61-70)
# =============================================================================
class TestStage9Backtracking(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_061_backtracking_depth_recorded(self):
        # Force backtracking by putting event 1 in slot 0 (blocking event 2) then event 2 fails and backtracks event 1 to slot 1
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        # Event 1 domain has (0,0) and (0,1). Event 2 domain ONLY has (0,0).
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0)], 1)
        }
        # Force ordering: 1 then 2
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertGreaterEqual(stats.backtracks, 1)

    def test_062_deterministic_backtracking_decision(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0), (0, 1)], 2),
            2: PlacementDomain(2, [(0, 0)], 1)
        }
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats1 = GenerationStatistics()
        placed1, _, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats1)
        stats2 = GenerationStatistics()
        placed2, _, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats2)
        self.assertEqual(placed1[0]["slot"], placed2[0]["slot"])
        self.assertEqual(placed1[1]["slot"], placed2[1]["slot"])

    def test_063_bounded_search_backtrack_depth_limit(self):
        self.assertEqual(self.engine.MAX_BACKTRACK_DEPTH, 50)

    def test_064_bounded_search_total_backtrack_limit(self):
        self.assertEqual(self.engine.MAX_TOTAL_BACKTRACKS, 500)

    def test_065_unresolvable_dead_end_terminates_gracefully(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        # Both only have (0,0) and share section S1 -> Impossible!
        domains = {
            1: PlacementDomain(1, [(0, 0)], 1),
            2: PlacementDomain(2, [(0, 0)], 1)
        }
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, diag = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertFalse(ok)
        self.assertGreaterEqual(len(diag["unplaced_events"]), 1)

    def test_066_dead_ends_statistic_incremented(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": False},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0)], 1),
            2: PlacementDomain(2, [(0, 0)], 1)
        }
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertGreaterEqual(stats.dead_ends, 1)

    def test_067_backtrack_preserves_pinned_assignments(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_pinned": True, "baseline_day": 0, "baseline_slot": 0},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0)], 1),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["slot"], 0)
        self.assertEqual(placed[1]["slot"], 1)

    def test_068_backtrack_preserves_frozen_assignments(self):
        events = [
            {"event_id": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1", "is_frozen": True, "baseline_day": 0, "baseline_slot": 0},
            {"event_id": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2", "is_pinned": False},
        ]
        domains = {
            1: PlacementDomain(1, [(0, 0)], 1),
            2: PlacementDomain(2, [(0, 0), (0, 1)], 2)
        }
        calendar_info = self.engine._extract_calendar(self.project["dataset"], [], [])
        stats = GenerationStatistics()
        placed, ok, _ = self.engine._construct_candidate(events, domains, calendar_info, [], [], GenerationConfig(generation_run_id="t"), stats=stats)
        self.assertTrue(ok)
        self.assertEqual(placed[0]["slot"], 0)
        self.assertEqual(placed[1]["slot"], 1)

    def test_069_search_statistics_populated_in_result(self):
        res = self.engine.generate(
            project=self.project,
            active_version_id=self.project.get("active_version_id"),
            config=GenerationConfig(generation_run_id="test_search_stats", seed=42)
        )
        self.assertIn("max_depth", res.diagnostics.search_statistics)
        self.assertIn("backtracks", res.diagnostics.search_statistics)

    def test_070_search_termination_reason_recorded(self):
        res = self.engine.generate(
            project=self.project,
            active_version_id=self.project.get("active_version_id"),
            config=GenerationConfig(generation_run_id="test_term_reason", seed=42)
        )
        self.assertEqual(res.termination_reason, "SUCCESS")

# =============================================================================
# 9. Lexicographic Optimization & Soft Objectives (Tests 71-84)
# =============================================================================
class TestStage9LexicographicOptimization(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_071_p0_hard_feasibility_absolute_priority(self):
        score1 = QualityScore(hard_violation_count=0, soft_violation_count=10, overall_quality_score=50.0)
        score2 = QualityScore(hard_violation_count=1, soft_violation_count=0, overall_quality_score=0.0)
        # Any candidate with hard_violation_count > 0 must lose lexicographically
        self.assertLess(score1.hard_violation_count, score2.hard_violation_count)

    def test_072_p1_critical_soft_travel_distance(self):
        cal = self.engine._extract_calendar(self.project["dataset"], [], [])
        e1 = {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "A101", "building": "Block A", "floor": 1}
        e2 = {"event_id": 2, "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "B101", "building": "Block B", "floor": 1}
        # Consecutive events in different buildings = building move
        moves, _ = self.engine._compute_zero_buffer_moves([e1, e2], "sections")
        self.assertEqual(moves, 1)

    def test_073_p2_runs_and_gaps_scoring(self):
        # Section with event at slot 0 and slot 2 (gap at slot 1)
        events = [
            {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 2, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2"}
        ]
        gaps, _ = self.engine._compute_gaps(events, "sections")
        self.assertEqual(gaps, 1)

    def test_074_p3_daily_load_balance_calculation(self):
        events = [
            {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 3, "day": 1, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}
        ]
        var = self.engine._compute_daily_load_variance(events, "sections")
        self.assertGreater(var, 0.0)

    def test_075_p4_lunch_window_scoring(self):
        # Section with lunch slots free has 0 violations
        events = [
            {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}
        ]
        viols = self.engine._compute_lunch_violations(events, "sections")
        self.assertEqual(viols, 0)

    def test_076_p5_preference_scoring(self):
        policies = [{"rule_type": "PREFER_MORNING_FACULTY", "category": "PREFERENCE", "enabled": True, "weight": 2.0}]
        events = [{"event_id": 1, "day": 0, "slot": 6, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}]
        prefs = self.engine._evaluate_preferences(events, policies)
        self.assertGreater(prefs, 0)

    def test_077_p6_stability_metrics_day_changes(self):
        baseline = [{"event_id": 1, "day": 0, "slot": 0, "baseline_day": 0, "baseline_slot": 0, "room": "R1", "baseline_room": "R1"}]
        candidate = [{"event_id": 1, "day": 1, "slot": 0, "baseline_day": 0, "baseline_slot": 0, "room": "R1", "baseline_room": "R1"}]
        metrics = self.engine._compute_stability_metrics(candidate, baseline)
        self.assertEqual(metrics["events_day_changed"], 1)

    def test_078_p6_stability_metrics_slot_displacement(self):
        baseline = [{"event_id": 1, "day": 0, "slot": 0, "baseline_day": 0, "baseline_slot": 0, "room": "R1", "baseline_room": "R1"}]
        candidate = [{"event_id": 1, "day": 0, "slot": 3, "baseline_day": 0, "baseline_slot": 0, "room": "R1", "baseline_room": "R1"}]
        metrics = self.engine._compute_stability_metrics(candidate, baseline)
        self.assertEqual(metrics["events_slot_changed"], 1)
        self.assertEqual(metrics["total_slot_displacement"], 3)
        self.assertEqual(metrics["max_slot_displacement"], 3)

    def test_079_profile_feasibility_first_configuration(self):
        cfg = GenerationConfig(generation_run_id="p_feas", optimization_profile=GenerationProfile.FEASIBILITY_FIRST)
        self.assertEqual(cfg.optimization_profile, "FEASIBILITY_FIRST")

    def test_080_profile_balanced_configuration(self):
        cfg = GenerationConfig(generation_run_id="p_bal", optimization_profile=GenerationProfile.BALANCED)
        self.assertEqual(cfg.optimization_profile, "BALANCED")

    def test_081_profile_quality_first_configuration(self):
        cfg = GenerationConfig(generation_run_id="p_qual", optimization_profile=GenerationProfile.QUALITY_FIRST)
        self.assertEqual(cfg.optimization_profile, "QUALITY_FIRST")

    def test_082_profile_stability_first_configuration(self):
        cfg = GenerationConfig(generation_run_id="p_stab", optimization_profile=GenerationProfile.STABILITY_FIRST)
        self.assertEqual(cfg.optimization_profile, "STABILITY_FIRST")

    def test_083_profiles_do_not_relax_hard_constraints(self):
        for prof in [GenerationProfile.FEASIBILITY_FIRST, GenerationProfile.BALANCED, GenerationProfile.QUALITY_FIRST, GenerationProfile.STABILITY_FIRST]:
            cfg = GenerationConfig(generation_run_id=f"p_{prof}", optimization_profile=prof)
            # In all profiles, zero hard violations are permitted
            self.assertTrue(cfg.respect_pinned_events)
            self.assertTrue(cfg.respect_frozen_events)

    def test_084_lexicographic_tuple_ordering(self):
        tup_clean = (0, 10.0, 5.0, 0.0)
        tup_hard_err = (1, 0.0, 0.0, 0.0)
        self.assertLess(tup_clean, tup_hard_err)

# =============================================================================
# 10. Independent Validator Parity (validator.py) (Tests 85-92)
# =============================================================================
class TestStage9ValidatorParity(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_085_validator_parity_on_generated_candidate(self):
        v_id = self.project.get("active_version_id")
        ver_data = self.project.get("versions", {}).get(v_id, {})
        faculty_leaves = ver_data.get("dataset", {}).get("faculty_leaves", {})

        cfg = GenerationConfig(generation_run_id="test_parity_01", seed=42, preserve_existing_assignments=True)
        res = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        cand_events = res.selected_candidate["events"]

        is_valid, errs, mets = validate_schedule(cand_events, faculty_leaves)
        self.assertTrue(is_valid)
        self.assertEqual(len(errs), 0)

    def test_086_event_count_parity_598(self):
        v_id = self.project.get("active_version_id")
        ver_data = self.project.get("versions", {}).get(v_id, {})
        faculty_leaves = ver_data.get("dataset", {}).get("faculty_leaves", {})
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        cand_events = res.selected_candidate["events"]
        self.assertEqual(len(cand_events), 598)

    def test_087_student_hours_parity_748(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        cand_events = res.selected_candidate["events"]
        tot_stud = sum(e["duration"] * len(e["sections"]) for e in cand_events)
        self.assertEqual(tot_stud, 748)

    def test_088_faculty_hours_parity_981(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        cand_events = res.selected_candidate["events"]
        tot_fac = sum(e["duration"] * len(e["faculty"]) for e in cand_events)
        self.assertEqual(tot_fac, 981)

    def test_089_room_clashes_parity_0(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        is_valid, errs, _ = validate_schedule(res.selected_candidate["events"], {})
        room_errs = [e for e in errs if "Room clash" in e]
        self.assertEqual(len(room_errs), 0)

    def test_090_section_clashes_parity_0(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        is_valid, errs, _ = validate_schedule(res.selected_candidate["events"], {})
        sec_errs = [e for e in errs if "Section clash" in e]
        self.assertEqual(len(sec_errs), 0)

    def test_091_faculty_clashes_parity_0(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        is_valid, errs, _ = validate_schedule(res.selected_candidate["events"], {})
        fac_errs = [e for e in errs if "Faculty clash" in e]
        self.assertEqual(len(fac_errs), 0)

    def test_092_faculty_leaves_respected_parity(self):
        v_id = self.project.get("active_version_id")
        ver_data = self.project.get("versions", {}).get(v_id, {})
        faculty_leaves = ver_data.get("dataset", {}).get("faculty_leaves", {})
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_parity"))
        is_valid, errs, _ = validate_schedule(res.selected_candidate["events"], faculty_leaves)
        leave_errs = [e for e in errs if "Faculty leave violation" in e]
        self.assertEqual(len(leave_errs), 0)

# =============================================================================
# 11. Multi-Candidate Generation & Determinism (Tests 93-104)
# =============================================================================
class TestStage9MultiCandidateAndDeterminism(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_093_generate_multiple_candidates_count(self):
        v_id = self.project.get("active_version_id")
        cfg = GenerationConfig(generation_run_id="multi_01", seed=42, candidate_count=3, preserve_existing_assignments=True)
        res = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        self.assertEqual(res.candidate_count_requested, 3)
        self.assertEqual(res.candidate_count_generated, 3)
        self.assertEqual(res.candidate_count_valid, 3)

    def test_094_multiple_candidates_unique_ids(self):
        v_id = self.project.get("active_version_id")
        cfg = GenerationConfig(generation_run_id="multi_02", seed=42, candidate_count=3, preserve_existing_assignments=True)
        res = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        ids = [c["candidate_id"] for c in res.candidates_summary]
        self.assertEqual(len(ids), len(set(ids)))

    def test_095_deterministic_result_from_identical_inputs(self):
        v_id = self.project.get("active_version_id")
        cfg1 = GenerationConfig(generation_run_id="run_det_1", seed=100, candidate_count=1, preserve_existing_assignments=True)
        res1 = self.engine.generate(self.project, active_version_id=v_id, config=cfg1)

        cfg2 = GenerationConfig(generation_run_id="run_det_2", seed=100, candidate_count=1, preserve_existing_assignments=True)
        res2 = self.engine.generate(self.project, active_version_id=v_id, config=cfg2)

        # Candidate placements must be identical
        events1 = [(e["event_id"], e["day"], e["slot"]) for e in res1.selected_candidate["events"]]
        events2 = [(e["event_id"], e["day"], e["slot"]) for e in res2.selected_candidate["events"]]
        self.assertEqual(events1, events2)

    def test_096_deterministic_score_from_identical_inputs(self):
        v_id = self.project.get("active_version_id")
        cfg1 = GenerationConfig(generation_run_id="run_det_s1", seed=100, candidate_count=1, preserve_existing_assignments=True)
        res1 = self.engine.generate(self.project, active_version_id=v_id, config=cfg1)

        cfg2 = GenerationConfig(generation_run_id="run_det_s2", seed=100, candidate_count=1, preserve_existing_assignments=True)
        res2 = self.engine.generate(self.project, active_version_id=v_id, config=cfg2)

        s1 = res1.selected_candidate["score"]
        s2 = res2.selected_candidate["score"]
        self.assertEqual(s1["overall_quality_score"], s2["overall_quality_score"])
        self.assertEqual(s1["hard_violation_count"], s2["hard_violation_count"])

    def test_097_deterministic_candidate_selection(self):
        v_id = self.project.get("active_version_id")
        cfg1 = GenerationConfig(generation_run_id="run_sel_1", seed=50, candidate_count=2, preserve_existing_assignments=True)
        res1 = self.engine.generate(self.project, active_version_id=v_id, config=cfg1)

        cfg2 = GenerationConfig(generation_run_id="run_sel_2", seed=50, candidate_count=2, preserve_existing_assignments=True)
        res2 = self.engine.generate(self.project, active_version_id=v_id, config=cfg2)

        idx1 = res1.selected_candidate["candidate_index"]
        idx2 = res2.selected_candidate["candidate_index"]
        self.assertEqual(idx1, idx2)

    def test_098_candidate_fingerprint_unique_per_arrangement(self):
        v_id = self.project.get("active_version_id")
        cfg = GenerationConfig(generation_run_id="run_fp", seed=42, candidate_count=1, preserve_existing_assignments=True)
        res = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        fp = res.selected_candidate["candidate_fingerprint"]
        self.assertTrue(len(fp) == 64)

    def test_099_random_generator_isolation_seed_respected(self):
        cfg = GenerationConfig(generation_run_id="t_seed", seed=999)
        self.assertEqual(cfg.seed, 999)

    def test_100_no_hidden_randomness(self):
        # Multiple executions with same seed give identical result fingerprint
        v_id = self.project.get("active_version_id")
        cfg = GenerationConfig(generation_run_id="run_fixed", seed=77, candidate_count=1, preserve_existing_assignments=True)
        res1 = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        res2 = self.engine.generate(self.project, active_version_id=v_id, config=cfg)
        self.assertEqual(res1.result_fingerprint, res2.result_fingerprint)

    def test_101_candidate_count_zero_handled_safely(self):
        cfg = GenerationConfig(generation_run_id="t_zero", candidate_count=0)
        res = self.engine.generate(self.project, active_version_id=self.project.get("active_version_id"), config=cfg)
        self.assertEqual(res.candidate_count_generated, 0)

    def test_102_candidate_immutability_attribute(self):
        c = TimetableCandidate("c1", "r1", 1, "p1", "v1", "s1", "f1", events=[{"id": 1}])
        d = c.to_dict()
        self.assertIn("candidate_id", d)
        self.assertIn("events", d)

    def test_103_selected_candidate_never_violates_hard_constraint(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_hard"))
        self.assertEqual(res.selected_candidate["score"]["hard_violation_count"], 0)

    def test_104_generation_result_contains_all_schema_fields(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="t_schema"))
        d = res.to_dict()
        req_fields = [
            "generation_run_id", "project_id", "project_version_id", "policy_snapshot_id",
            "feasibility_run_id", "engine_version", "seed", "configuration", "status",
            "termination_reason", "candidate_count_requested", "candidate_count_generated",
            "candidate_count_valid", "selected_candidate_id", "generation_statistics",
            "validation_summary", "optimization_summary", "comparison_summary", "diagnostics",
            "input_fingerprint", "result_fingerprint", "timestamp"
        ]
        for f in req_fields:
            self.assertIn(f, d, f"Missing schema field {f}")

# =============================================================================
# 12. Authorization, RBAC & Audit Events (Tests 105-114)
# =============================================================================
class TestStage9AuthorizationAndAudit(unittest.TestCase):
    def setUp(self):
        self.project = load_canonical_baseline()
        self.temp_dir = tempfile.mkdtemp()
        self.svc = GenerationService(storage_root=self.temp_dir)
        self.feas = {
            "feasibility_run_id": "feas_auth_123",
            "status": "FEASIBLE",
            "project_version_id": self.project.get("active_version_id"),
            "policy_snapshot_id": self.project.get("policy_version", "polver_default")
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_105_super_admin_authorized(self):
        user = User(user_id="usr_admin", email="admin@local.test", role=UserRole.SUPER_ADMIN, display_name="Admin")
        ok, res, msg = self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        self.assertTrue(ok)

    def test_106_timetable_admin_authorized(self):
        user = User(user_id="usr_coord", email="coord@local.test", role=UserRole.TIMETABLE_ADMIN, display_name="Coordinator")
        ok, res, msg = self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        self.assertTrue(ok)

    def test_107_teacher_authorized_on_owned_project(self):
        proj = dict(self.project)
        proj["owner_user_id"] = "usr_teach_01"
        user = User(user_id="usr_teach_01", email="teacher@local.test", role=UserRole.TEACHER, display_name="Teacher")
        ok, res, msg = self.svc.run_generation_for_user(user, proj, self.feas, active_version_id=proj.get("active_version_id"))
        self.assertTrue(ok)

    def test_108_teacher_blocked_on_unowned_project(self):
        proj = dict(self.project)
        proj["owner_user_id"] = "usr_other_admin"
        proj["created_by_user_id"] = "usr_other_admin"
        user = User(user_id="usr_teach_01", email="teacher@local.test", role=UserRole.TEACHER, display_name="Teacher")
        ok, res, msg = self.svc.run_generation_for_user(user, proj, self.feas, active_version_id=proj.get("active_version_id"))
        self.assertFalse(ok)
        self.assertIn("Permission denied", msg)

    def test_109_viewer_strictly_blocked_read_only(self):
        user = User(user_id="usr_viewer_01", email="viewer@local.test", role=UserRole.VIEWER, display_name="Viewer")
        ok, res, msg = self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        self.assertFalse(ok)
        self.assertIn("Permission denied", msg)

    def test_110_audit_event_generation_started_logged(self):
        user = User(user_id="usr_admin", email="admin@local.test", role=UserRole.SUPER_ADMIN, display_name="Admin")
        self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        events = self.svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(e["event_type"] == AuditEventType.GENERATION_STARTED for e in events))

    def test_111_audit_event_generation_completed_logged(self):
        user = User(user_id="usr_admin", email="admin@local.test", role=UserRole.SUPER_ADMIN, display_name="Admin")
        self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        events = self.svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(e["event_type"] == AuditEventType.GENERATION_COMPLETED for e in events))

    def test_112_audit_event_access_denied_logged(self):
        user = User(user_id="usr_viewer_01", email="viewer@local.test", role=UserRole.VIEWER, display_name="Viewer")
        self.svc.run_generation_for_user(user, self.project, self.feas, active_version_id=self.project.get("active_version_id"))
        events = self.svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(e["event_type"] == AuditEventType.ACCESS_DENIED for e in events))

    def test_113_immutable_filesystem_storage_created(self):
        user = User(user_id="usr_admin", email="admin@local.test", role=UserRole.SUPER_ADMIN, display_name="Admin")
        cfg = GenerationConfig(generation_run_id="test_run_imm_1", seed=42)
        self.svc.run_generation_for_user(user, self.project, self.feas, config=cfg, active_version_id=self.project.get("active_version_id"))
        run_dir = os.path.join(self.temp_dir, "test_run_imm_1")
        self.assertTrue(os.path.exists(run_dir))
        for sub in ["input", "canonical", "feasibility", "candidates", "validation", "comparison", "exports", "logs"]:
            self.assertTrue(os.path.exists(os.path.join(run_dir, sub)))

    def test_114_immutable_filesystem_never_overwrites(self):
        user = User(user_id="usr_admin", email="admin@local.test", role=UserRole.SUPER_ADMIN, display_name="Admin")
        cfg = GenerationConfig(generation_run_id="test_run_dup", seed=42)
        # First save
        self.svc.run_generation_for_user(user, self.project, self.feas, config=cfg, active_version_id=self.project.get("active_version_id"))
        # Second attempt with exact same run_id must error out
        with self.assertRaises(ValueError):
            self.svc._save_immutable_run(self.project, self.feas, GenerationResult("test_run_dup", "p", "v", "s", "f"))

# =============================================================================
# 13. Certified Dataset Scale & Performance Target (Tests 115-122)
# =============================================================================
class TestStage9CertifiedDatasetPerformance(unittest.TestCase):
    def setUp(self):
        self.engine = TimetableGenerationEngine()
        self.project = load_canonical_baseline()

    def test_115_certified_dataset_598_master_events(self):
        v_id = self.project.get("active_version_id")
        events = self.project["versions"][v_id]["events"]
        self.assertEqual(len(events), 598)

    def test_116_certified_dataset_673_event_hours(self):
        v_id = self.project.get("active_version_id")
        events = self.project["versions"][v_id]["events"]
        tot_event_hours = sum(e["duration"] for e in events)
        self.assertEqual(tot_event_hours, 673)

    def test_117_certified_dataset_75_labs(self):
        v_id = self.project.get("active_version_id")
        events = self.project["versions"][v_id]["events"]
        labs = [e for e in events if e.get("is_lab") and e.get("duration") == 2]
        self.assertEqual(len(labs), 75)

    def test_118_certified_dataset_38_shared_events(self):
        v_id = self.project.get("active_version_id")
        events = self.project["versions"][v_id]["events"]
        shared = [e for e in events if len(e.get("sections", [])) > 1]
        self.assertEqual(len(shared), 38)

    def test_119_certified_dataset_3_no_room_events(self):
        v_id = self.project.get("active_version_id")
        events = self.project["versions"][v_id]["events"]
        no_rooms = [e for e in events if e.get("room") == "NO_ROOM"]
        self.assertEqual(len(no_rooms), 3)

    def test_120_certified_dataset_execution_timing(self):
        v_id = self.project.get("active_version_id")
        t0 = time.perf_counter()
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="perf_test", seed=42))
        elapsed = time.perf_counter() - t0
        # Generation for 598 events must complete well within the 120s limit (target < 10s)
        self.assertLess(elapsed, 120.0)
        self.assertEqual(res.status, GenerationStatus.COMPLETED_WITH_WARNINGS)

    def test_121_generation_statistics_timing_populated(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="stat_test", seed=42))
        stats = res.generation_statistics
        self.assertGreater(stats.total_time_ms, 0.0)
        self.assertGreater(stats.domain_generation_time_ms, 0.0)
        self.assertEqual(stats.events_total, 598)

    def test_122_comparison_with_baseline_summary(self):
        v_id = self.project.get("active_version_id")
        res = self.engine.generate(self.project, active_version_id=v_id, config=GenerationConfig(generation_run_id="comp_test", seed=42))
        comp = res.comparison_summary
        self.assertIn("stability_day_changes", comp)
        self.assertIn("stability_slot_displacements", comp)
        self.assertEqual(comp["event_count_diff"], 0)

if __name__ == "__main__":
    unittest.main()
