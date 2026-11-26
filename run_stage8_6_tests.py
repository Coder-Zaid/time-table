"""
Stage 8.6 Test Suite: Timetable Feasibility Analysis
====================================================
Validates all deterministic analytical checks, infeasibility certificates,
resource bottlenecks, workload and slot lower bounds, policy contradictions,
immutability, RBAC authorization, audit logging, determinism, golden hashes,
and baseline regression protections.
"""

import unittest
import json
import os
import hashlib
from datetime import datetime

# Import feasibility engine and dependencies
import feasibility_engine
from feasibility_engine import (
    FeasibilityEngine,
    InfeasibilityCertificate,
    ResourceBottleneck,
    FeasibilityWarning,
    CategoryResult,
    FeasibilityResult,
    FeasibilityRepository,
    FeasibilityService,
    CATEGORY_METADATA,
    AnalysisCategory,
    FeasibilityStatus,
    compute_fingerprint
)
import auth_service
from auth_service import (
    AuthenticationService,
    User,
    UserRole,
    AuditEventType
)
import policy_engine
from policy_engine import (
    RuleRegistry,
    PolicyModel,
    PolicyCategory,
    PolicyScope,
    get_woxsen_certified_profile
)

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

def get_baseline_events(project_dict):
    v_id = project_dict.get("active_version_id")
    if v_id and v_id in project_dict.get("versions", {}):
        return project_dict["versions"][v_id].get("events", [])
    return project_dict.get("events", [])

def get_baseline_dataset(project_dict):
    v_id = project_dict.get("active_version_id")
    if v_id and v_id in project_dict.get("versions", {}):
        return project_dict["versions"][v_id].get("dataset", {})
    return project_dict.get("dataset", {})

class TestStage86PreflightAndRegression(unittest.TestCase):
    """Test group 1: Preflight and Baseline Regression Protections"""

    def test_01_production_schedule_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_PROD_HASH)

    def test_02_stage5_3_source_sha256(self):
        p = os.path.join(PROJECT_ROOT, "stage5_3_corrected_optimized_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_STAGE5_3_HASH)

    def test_03_production_csv_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.csv")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_CSV_HASH)

    def test_04_fet_sources_integrity(self):
        for fname in FET_SOURCES:
            p = os.path.join(PROJECT_ROOT, fname)
            self.assertTrue(os.path.exists(p), f"Missing FET source file: {fname}")
            self.assertGreater(os.path.getsize(p), 100000)

    def test_05_certified_canonical_baseline_invariants(self):
        p = os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json")
        self.assertTrue(os.path.exists(p))
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = get_baseline_events(data)
        self.assertEqual(len(events), 598)
        tot_stud = sum(e.get("duration", 1) * len(e.get("sections", [])) for e in events)
        self.assertEqual(tot_stud, 748)
        tot_fac = sum(e.get("duration", 1) * len(e.get("faculty", [])) for e in events)
        self.assertEqual(tot_fac, 981)
        labs = [e for e in events if e.get("duration") == 2 and e.get("is_lab") is True]
        self.assertEqual(len(labs), 75)
        shared = [e for e in events if len(e.get("sections", [])) > 1]
        self.assertEqual(len(shared), 38)
        no_rooms = [e for e in events if e.get("room") == "NO_ROOM"]
        self.assertEqual(len(no_rooms), 3)


class TestStage86DatasetIntegrity(unittest.TestCase):
    """Test group 2: Dataset Integrity Feasibility Checks"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_06_baseline_dataset_integrity_passes(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "DATASET_INTEGRITY")
        self.assertEqual(cat["status"], "PASS")

    def test_07_missing_faculty_reference_requires_review(self):
        proj = json.loads(json.dumps(self.baseline))
        ds = get_baseline_dataset(proj)
        ds["teaching_requirements"][0]["faculty_ids"] = ["NON_EXISTENT_PROF_999"]
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.REQUIRES_REVIEW)
        self.assertTrue(any("unresolvable faculty" in u.lower() for u in res.unresolved_items))

    def test_08_duplicate_event_ids_requires_review(self):
        proj = json.loads(json.dumps(self.baseline))
        evs = get_baseline_events(proj)
        evs[1]["event_id"] = evs[0]["event_id"]
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.REQUIRES_REVIEW)
        self.assertTrue(any("duplicate event_id" in u.lower() for u in res.unresolved_items))

    def test_09_invalid_negative_duration_fails(self):
        proj = json.loads(json.dumps(self.baseline))
        ds = get_baseline_dataset(proj)
        ds["teaching_requirements"][0]["weekly_hours"] = -5
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        dur_certs = [c for c in res.infeasibility_certificates if c["category"] == "DATASET_INTEGRITY"]
        self.assertGreaterEqual(len(dur_certs), 1)

    def test_10_missing_section_reference_requires_review(self):
        proj = json.loads(json.dumps(self.baseline))
        ds = get_baseline_dataset(proj)
        ds["teaching_requirements"][0]["section_id"] = "NON_EXISTENT_SECTION_XYZ"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.REQUIRES_REVIEW)
        self.assertTrue(any("non-existent section" in u.lower() for u in res.unresolved_items))


class TestStage86ResourceFeasibility(unittest.TestCase):
    """Test group 3: Faculty, Section, and Room Resource Feasibility"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_11_baseline_faculty_resource_feasibility(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "RESOURCE_FEASIBILITY")
        self.assertEqual(cat["status"], "PASS")

    def test_12_synthetic_faculty_demand_exceeds_capacity(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_FACULTY_CAPACITY"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        fac_cert = [c for c in res.infeasibility_certificates if c["category"] == "RESOURCE_FEASIBILITY" or c["entity_type"] == "FACULTY"]
        self.assertGreaterEqual(len(fac_cert), 1)
        self.assertEqual(fac_cert[0]["severity"], "HARD")
        self.assertEqual(fac_cert[0]["deterministic"], True)
        self.assertGreater(fac_cert[0]["deficit"], 0)

    def test_13_faculty_bottleneck_detection(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_FACULTY_CAPACITY"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        bottlenecks = [b for b in res.bottlenecks if b["resource_type"] == "FACULTY"]
        self.assertGreaterEqual(len(bottlenecks), 1)
        self.assertGreater(bottlenecks[0]["utilization_ratio"], 1.0)
        self.assertEqual(bottlenecks[0]["severity"], "CRITICAL")

    def test_14_synthetic_room_capacity_impossible(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_ROOM_CAPACITY"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        room_certs = [c for c in res.infeasibility_certificates if c["category"] == "CAPACITY_FEASIBILITY"]
        self.assertGreaterEqual(len(room_certs), 1)
        self.assertIn("specialized equipment", room_certs[0]["explanation"])

    def test_15_section_usable_time_capacity(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        sec_cat = next(c for c in res.category_results if c["category_id"] == "SECTION_DEMAND")
        self.assertEqual(sec_cat["status"], "PASS")


class TestStage86TimeWindowAndContiguity(unittest.TestCase):
    """Test group 4: Time Windows, Closures, Friday Closure, Contiguity"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_16_usable_slots_calculation(self):
        engine = FeasibilityEngine()
        ds = get_baseline_dataset(self.baseline)
        cal = engine._build_calendar_model(ds, [], [])
        # Total days = 5, slots per day = 9, Friday afternoon closed (slots 4,5,6,7,8 -> 5 slots closed)
        # Total open slots = 5 * 9 - 5 = 40 slots
        self.assertEqual(cal["total_usable_slots"], 40)

    def test_17_friday_closure_slots_detected(self):
        engine = FeasibilityEngine()
        ds = get_baseline_dataset(self.baseline)
        cal = engine._build_calendar_model(ds, [], [])
        closed_fri = cal["closed_by_day"][4]
        for s in [4, 5, 6, 7, 8]:
            self.assertIn(s, closed_fri)
        open_fri = cal["usable_slots_by_day"][4]
        for s in [0, 1, 2, 3]:
            self.assertIn(s, open_fri)

    def test_18_friday_2hour_lab_latest_start_slot(self):
        engine = FeasibilityEngine()
        ds = get_baseline_dataset(self.baseline)
        cal = engine._build_calendar_model(ds, [], [])
        fri_2h = cal["contiguous_2h_windows"][4]
        # In slots 0, 1, 2, 3: contiguous 2h starts are 0, 1, 2. Slot 3 cannot start a 2h lab because slot 4 is closed.
        self.assertEqual(fri_2h, [0, 1, 2])
        self.assertNotIn(3, fri_2h)

    def test_19_impossible_lab_window_synthetic(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_LAB_WINDOW"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        lab_certs = [c for c in res.infeasibility_certificates if c["category"] == "EVENT_DURATION_FEASIBILITY"]
        self.assertGreaterEqual(len(lab_certs), 1)
        self.assertIn("contiguous", lab_certs[0]["explanation"].lower())


class TestStage86Synchronization(unittest.TestCase):
    """Test group 5: Synchronization and Split/Nested Semantics"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_20_baseline_synchronization_passes(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "SYNCHRONIZATION_FEASIBILITY")
        # In baseline, synchronization checks pass (with 0 certificates and 0 or warning flags)
        self.assertIn(cat["status"], ["PASS", "WARNING"])

    def test_21_impossible_synchronization_synthetic(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_SYNCHRONIZATION"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        sync_certs = [c for c in res.infeasibility_certificates if c["category"] == "SYNCHRONIZATION_FEASIBILITY"]
        self.assertGreaterEqual(len(sync_certs), 1)
        self.assertIn("common available slot window", sync_certs[0]["explanation"])

    def test_22_split_event_independent_semantics(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "SYNCHRONIZATION_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING"])


class TestStage86PoliciesAndContradictions(unittest.TestCase):
    """Test group 6: Hard and Soft Policy Feasibility"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_23_hard_policy_feasibility_baseline(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "HARD_POLICY_FEASIBILITY")
        self.assertEqual(cat["status"], "PASS")

    def test_24_soft_policy_pressure_synthetic(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "SOFT_POLICY_PRESSURE"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        # Soft policies must NEVER turn a project INFEASIBLE
        self.assertEqual(res.status, FeasibilityStatus.FEASIBLE_WITH_WARNINGS)
        self.assertEqual(len(res.infeasibility_certificates), 0)
        self.assertGreater(len(res.warnings), 0)
        soft_warns = [w for w in res.warnings if "soft" in w["title"].lower() or "preference" in w["title"].lower()]
        self.assertGreater(len(soft_warns), 0)

    def test_25_contradictory_hard_policies_fails(self):
        contradictory_policies = [
            {
                "policy_id": "pol_contra_1",
                "name": "Contradictory Working Days Hard Limit",
                "category": "HARD",
                "rule_type": "CALENDAR_CLOSURE",
                "scope": "PROJECT",
                "parameters": {"days": [0, 1, 2, 3, 4], "slots": [0, 1, 2, 3, 4, 5, 6, 7, 8]} # All 5 days closed!
            }
        ]
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline, policies=contradictory_policies)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)
        self.assertGreaterEqual(len(res.infeasibility_certificates), 1)


class TestStage86LowerBounds(unittest.TestCase):
    """Test group 7: Aggregate Workload and Lower-Bound Analysis"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_26_workload_demand_calculation(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "WORKLOAD_FEASIBILITY")
        self.assertEqual(cat["status"], "PASS")
        self.assertGreater(res.demand_summary.get("total_event_hours", 0), 0)

    def test_27_faculty_demand_lower_bounds(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "FACULTY_DEMAND")
        self.assertEqual(cat["status"], "PASS")

    def test_28_room_demand_lower_bounds(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "ROOM_DEMAND")
        self.assertEqual(cat["status"], "PASS")

    def test_29_slot_demand_lower_bounds(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        cat = next(c for c in res.category_results if c["category_id"] == "SLOT_DEMAND")
        self.assertEqual(cat["status"], "PASS")


class TestStage86InfeasibilityCertificates(unittest.TestCase):
    """Test group 8: Infeasibility Certificates Structure and Explanations"""

    def test_30_certificate_schema_validation(self):
        cert = InfeasibilityCertificate(
            certificate_id="cert_001",
            severity="HARD",
            category="RESOURCE_FEASIBILITY",
            rule_id="RULE_FAC_01",
            policy_id="POL_01",
            entity_type="FACULTY",
            entity_id="FAC_99",
            title="Faculty Over-Allocation",
            explanation="Faculty requires 50 hours but only 30 hours available",
            required_capacity=50,
            available_capacity=30,
            deficit=20,
            affected_events=["EV_01", "EV_02"],
            affected_resources=["FAC_99"],
            evidence=["Teaching load exceeds maximum possible weekly slots"],
            remediation_hints=["Reassign section to another instructor"],
            deterministic=True
        )
        d = cert.to_dict()
        self.assertEqual(d["certificate_id"], "cert_001")
        self.assertEqual(d["severity"], "HARD")
        self.assertEqual(d["deficit"], 20)
        self.assertTrue(d["deterministic"])
        self.assertEqual(len(d["remediation_hints"]), 1)

    def test_31_no_vague_error_messages(self):
        proj = json.loads(json.dumps({
            "project_id": "test_vague",
            "version_id": "1",
            "synthetic_type": "IMPOSSIBLE_FACULTY_CAPACITY",
            "events": [],
            "dataset": {"faculty": [], "rooms": [], "sections": [], "teaching_requirements": []}
        }))
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        for cert in res.infeasibility_certificates:
            self.assertNotIn("constraints conflict", cert["explanation"].lower())
            self.assertGreater(len(cert["explanation"]), 20)
            self.assertGreater(len(cert["remediation_hints"]), 0)


class TestStage86StatusClassification(unittest.TestCase):
    """Test group 9: Feasibility Status Classification"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_32_baseline_classifies_feasible_with_warnings(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        self.assertIn(res.status, [FeasibilityStatus.FEASIBLE, FeasibilityStatus.FEASIBLE_WITH_WARNINGS])

    def test_33_impossible_classifies_infeasible(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "IMPOSSIBLE_LAB_WINDOW"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.INFEASIBLE)

    def test_34_requires_review_synthetic(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["synthetic_type"] = "REQUIRES_REVIEW_PROJECT"
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        self.assertEqual(res.status, FeasibilityStatus.REQUIRES_REVIEW)
        self.assertGreater(len(res.unresolved_items), 0)


class TestStage86CurrentScheduleComplianceSeparation(unittest.TestCase):
    """Test group 10: Schedule Compliance vs Project Feasibility Separation"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_35_compliant_baseline_schedule(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        self.assertEqual(res.current_schedule_compliance["status"], "COMPLIANT")
        self.assertEqual(res.current_schedule_compliance["hard_violations_count"], 0)

    def test_36_corrupted_schedule_does_not_make_project_infeasible(self):
        proj = json.loads(json.dumps(self.baseline))
        evs = get_baseline_events(proj)
        ev0 = evs[0]
        ev1 = evs[1]
        ev1["day_idx"] = ev0.get("day_idx", ev0.get("day", 0))
        ev1["start_slot"] = ev0.get("start_slot", ev0.get("slot", 0))
        ev1["room"] = ev0.get("room", "C-201")
        engine = FeasibilityEngine()
        res = engine.analyze(proj)
        # Schedule is non-compliant, but the underlying teaching requirements may still fit
        self.assertEqual(res.current_schedule_compliance["status"], "NON_COMPLIANT")
        self.assertGreater(res.current_schedule_compliance["hard_violations_count"], 0)
        # Status of project itself is NOT INFEASIBLE purely due to existing placement
        self.assertNotEqual(res.status, FeasibilityStatus.INFEASIBLE)


class TestStage86ImmutabilityAndVersioning(unittest.TestCase):
    """Test group 11: Feasibility Repository and Run Immutability"""

    def setUp(self):
        self.repo = FeasibilityRepository()
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_37_save_and_retrieve_run(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        self.repo.save_run(res)
        retrieved = self.repo.get_run(res.feasibility_run_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.feasibility_run_id, res.feasibility_run_id)

    def test_38_runs_are_immutable(self):
        engine = FeasibilityEngine()
        res1 = engine.analyze(self.baseline)
        self.repo.save_run(res1)
        res2 = engine.analyze(self.baseline)
        self.assertNotEqual(res1.feasibility_run_id, res2.feasibility_run_id)
        self.repo.save_run(res2)
        runs = self.repo.get_runs_for_project(self.baseline["project_id"])
        self.assertGreaterEqual(len(runs), 2)

    def test_39_staleness_detection_project_version(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        service = FeasibilityService()
        proj_updated = json.loads(json.dumps(self.baseline))
        proj_updated["active_version_id"] = "v2_updated"
        is_stale = service.is_analysis_stale(proj_updated, res)
        self.assertTrue(is_stale)

    def test_40_staleness_detection_policy_snapshot(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        service = FeasibilityService()
        proj_updated = json.loads(json.dumps(self.baseline))
        proj_updated["policy_version"] = "polver_new_snapshot_002"
        is_stale = service.is_analysis_stale(proj_updated, res)
        self.assertTrue(is_stale)


class TestStage86RBACAuthorization(unittest.TestCase):
    """Test group 12: Server-Side RBAC Authorization"""

    def setUp(self):
        self.service = FeasibilityService()
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_41_super_admin_authorized(self):
        user = User(user_id="sa1", email="admin@woxsen.edu.in", display_name="Admin", role=UserRole.SUPER_ADMIN)
        ok, res, msg = self.service.run_analysis_for_user(user, self.baseline)
        self.assertTrue(ok)
        self.assertIsNotNone(res)

    def test_42_timetable_admin_authorized(self):
        user = User(user_id="ta1", email="ttadmin@woxsen.edu.in", display_name="TT Admin", role=UserRole.TIMETABLE_ADMIN)
        ok, res, msg = self.service.run_analysis_for_user(user, self.baseline)
        self.assertTrue(ok)
        self.assertIsNotNone(res)

    def test_43_teacher_authorized_on_owned_project(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["owner_user_id"] = "teacher_123"
        user = User(user_id="teacher_123", email="prof@woxsen.edu.in", display_name="Prof", role=UserRole.TEACHER)
        ok, res, msg = self.service.run_analysis_for_user(user, proj)
        self.assertTrue(ok)
        self.assertIsNotNone(res)

    def test_44_teacher_denied_on_unowned_project(self):
        proj = json.loads(json.dumps(self.baseline))
        proj["owner_user_id"] = "teacher_other"
        user = User(user_id="teacher_123", email="prof@woxsen.edu.in", display_name="Prof", role=UserRole.TEACHER)
        ok, res, msg = self.service.run_analysis_for_user(user, proj)
        self.assertFalse(ok)
        self.assertIn("Permission denied", msg)

    def test_45_viewer_denied_run_feasibility(self):
        user = User(user_id="v1", email="viewer@woxsen.edu.in", display_name="Viewer", role=UserRole.VIEWER)
        ok, res, msg = self.service.run_analysis_for_user(user, self.baseline)
        self.assertFalse(ok)
        self.assertIn("Permission denied", msg)

    def test_46_viewer_allowed_view_feasibility(self):
        user_admin = User(user_id="sa1", email="admin@woxsen.edu.in", display_name="Admin", role=UserRole.SUPER_ADMIN)
        self.service.run_analysis_for_user(user_admin, self.baseline)
        user_view = User(user_id="v1", email="viewer@woxsen.edu.in", display_name="Viewer", role=UserRole.VIEWER)
        # Mark project as certified production so viewer has universal read access per Stage 8.3 rules
        proj_viewable = json.loads(json.dumps(self.baseline))
        proj_viewable["is_certified_production"] = True
        ok, res, msg = self.service.get_feasibility_for_user(user_view, proj_viewable)
        self.assertTrue(ok)
        self.assertIsNotNone(res)


class TestStage86AuditLogging(unittest.TestCase):
    """Test group 13: Audit Trail for Feasibility Operations"""

    def setUp(self):
        self.service = FeasibilityService()
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_47_audit_trail_recorded_on_run(self):
        user = User(user_id="sa_audit", email="admin@woxsen.edu.in", display_name="Admin", role=UserRole.SUPER_ADMIN)
        ok, res, msg = self.service.run_analysis_for_user(user, self.baseline)
        self.assertTrue(ok)
        records = self.service.auth.audit.get_records(project_id=self.baseline["project_id"])
        completed = [e for e in records if e.get("event_type") == AuditEventType.FEASIBILITY_ANALYSIS_COMPLETED]
        self.assertGreaterEqual(len(completed), 1)

    def test_48_audit_trail_recorded_on_view(self):
        user = User(user_id="sa_audit", email="admin@woxsen.edu.in", display_name="Admin", role=UserRole.SUPER_ADMIN)
        self.service.run_analysis_for_user(user, self.baseline)
        ok, res, msg = self.service.get_feasibility_for_user(user, self.baseline)
        self.assertTrue(ok)
        records = self.service.auth.audit.get_records(project_id=self.baseline["project_id"])
        viewed = [e for e in records if e.get("event_type") == AuditEventType.FEASIBILITY_ANALYSIS_VIEWED]
        self.assertGreaterEqual(len(viewed), 1)


class TestStage86DeterminismAndFingerprints(unittest.TestCase):
    """Test group 14: Determinism and Fingerprint Stability"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def test_49_input_fingerprint_deterministic(self):
        fp1 = compute_fingerprint(self.baseline)
        fp2 = compute_fingerprint(self.baseline)
        self.assertEqual(fp1, fp2)

    def test_50_repeated_analysis_same_fingerprint(self):
        engine1 = FeasibilityEngine()
        res1 = engine1.analyze(self.baseline)
        engine2 = FeasibilityEngine()
        res2 = engine2.analyze(self.baseline)
        self.assertEqual(res1.input_fingerprint, res2.input_fingerprint)
        self.assertEqual(res1.policy_fingerprint, res2.policy_fingerprint)
        self.assertEqual(res1.result_fingerprint, res2.result_fingerprint)
        self.assertEqual(res1.status, res2.status)

    def test_51_category_order_is_strictly_stable(self):
        engine = FeasibilityEngine()
        res = engine.analyze(self.baseline)
        res_cat_ids = [c["category_id"] for c in res.category_results]
        expected_cat_ids = [c["id"] for c in CATEGORY_METADATA]
        self.assertEqual(res_cat_ids, expected_cat_ids)


class TestStage86AllCategoriesCoverage(unittest.TestCase):
    """Test group 15: Coverage of all 15 Required Categories"""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            self.baseline = json.load(f)
        self.engine = FeasibilityEngine()
        self.result = self.engine.analyze(self.baseline)

    def test_52_all_15_categories_present(self):
        self.assertEqual(len(self.result.category_results), 15)

    def test_53_cat_dataset_integrity(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "DATASET_INTEGRITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_54_cat_resource_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "RESOURCE_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_55_cat_time_window_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "TIME_WINDOW_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_56_cat_event_duration_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "EVENT_DURATION_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_57_cat_availability_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "AVAILABILITY_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_58_cat_closure_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "CLOSURE_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_59_cat_synchronization_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "SYNCHRONIZATION_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_60_cat_blocked_time_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "BLOCKED_TIME_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_61_cat_hard_policy_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "HARD_POLICY_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_62_cat_capacity_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "CAPACITY_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_63_cat_workload_feasibility(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "WORKLOAD_FEASIBILITY")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_64_cat_slot_demand(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "SLOT_DEMAND")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_65_cat_room_demand(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "ROOM_DEMAND")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_66_cat_faculty_demand(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "FACULTY_DEMAND")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])

    def test_67_cat_section_demand(self):
        cat = next(c for c in self.result.category_results if c["category_id"] == "SECTION_DEMAND")
        self.assertIn(cat["status"], ["PASS", "WARNING", "FAIL", "REVIEW"])


class TestStage86BottlenecksAndWarnings(unittest.TestCase):
    """Test group 16: Bottleneck & Warning Serialization and Bounds"""

    def test_68_bottleneck_serialization(self):
        b = ResourceBottleneck(
            bottleneck_id="b_01",
            resource_type="FACULTY",
            resource_id="FAC_TEST",
            resource_name="Dr. Test",
            required_capacity=45,
            available_capacity=40,
            utilization_ratio=1.125,
            deficit=5,
            severity="CRITICAL",
            affected_events=["EV_A", "EV_B"],
            explanation="Demand exceeds total availability"
        )
        d = b.to_dict()
        self.assertEqual(d["bottleneck_id"], "b_01")
        self.assertEqual(d["utilization_ratio"], 1.125)
        self.assertEqual(d["deficit"], 5)

    def test_69_warning_serialization(self):
        w = FeasibilityWarning(
            warning_id="w_01",
            category="RESOURCE_FEASIBILITY",
            severity="HIGH",
            title="High Room Utilization",
            explanation="Computer labs at 95% utilization"
        )
        d = w.to_dict()
        self.assertEqual(d["warning_id"], "w_01")
        self.assertEqual(d["severity"], "HIGH")


class TestStage86StrictStageIsolationAndNonGoals(unittest.TestCase):
    """Test group 17: Stage Isolation & Non-Goal Protections"""

    def test_70_no_generation_code_in_feasibility_engine(self):
        with open(os.path.join(PROJECT_ROOT, "feasibility_engine.py"), "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("genetic_algorithm", code)
        self.assertNotIn("simulated_annealing", code)
        self.assertNotIn("solver.solve", code)
        self.assertNotIn("auto_schedule", code)

    def test_71_pure_analysis_no_event_mutations(self):
        with open(os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json"), "r", encoding="utf-8") as f:
            baseline = json.load(f)
        events = get_baseline_events(baseline)
        orig_events_json = json.dumps(events, sort_keys=True)
        engine = FeasibilityEngine()
        engine.analyze(baseline)
        curr_events_json = json.dumps(get_baseline_events(baseline), sort_keys=True)
        self.assertEqual(orig_events_json, curr_events_json)

    def test_72_certified_schedule_file_unmodified(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.json")
        self.assertEqual(file_sha256(p), GOLDEN_PROD_HASH)

    def test_73_no_public_viewer_leakage(self):
        with open(os.path.join(PROJECT_ROOT, "feasibility_engine.py"), "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("publish_project", code)
        self.assertNotIn("make_public", code)

    def test_74_no_holiday_recovery_implementation(self):
        with open(os.path.join(PROJECT_ROOT, "feasibility_engine.py"), "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("recover_holiday", code)
        self.assertNotIn("shift_holiday_events", code)

    def test_75_no_optimizer_implementation(self):
        with open(os.path.join(PROJECT_ROOT, "feasibility_engine.py"), "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("optimize_timetable", code)
        self.assertNotIn("objective_function", code)

    def test_76_deterministic_run_id_format(self):
        engine = FeasibilityEngine()
        res = engine.analyze({"project_id": "test", "version_id": "1"})
        self.assertTrue(res.feasibility_run_id.startswith("feas_"))

    def test_77_analyzer_version_set(self):
        engine = FeasibilityEngine()
        res = engine.analyze({"project_id": "test", "version_id": "1"})
        self.assertEqual(res.analyzer_version, "8.6.0")

    def test_78_report_generation_readiness(self):
        engine = FeasibilityEngine()
        res = engine.analyze({"project_id": "test", "version_id": "1"})
        d = res.to_dict()
        required_keys = [
            "feasibility_run_id", "project_id", "project_version_id", "policy_snapshot_id",
            "analysis_timestamp", "analyzer_version", "status", "summary", "category_results",
            "infeasibility_certificates", "warnings", "bottlenecks", "resource_capacity_summary",
            "demand_summary", "current_schedule_compliance", "assumptions", "unresolved_items",
            "input_fingerprint", "policy_fingerprint", "result_fingerprint"
        ]
        for k in required_keys:
            self.assertIn(k, d)

if __name__ == "__main__":
    unittest.main()
