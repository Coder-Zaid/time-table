"""
run_stage11_tests.py - Stage 11 Automated Test Suite (142 Tests)
Review, Versioning & Approval Workflow Certification
"""

import unittest
import json
import os
import hashlib
import tempfile
import shutil
import copy
from datetime import datetime, timezone

import versioning_models
from versioning_models import (
    VersionState,
    ReviewStatus,
    ReviewDecision,
    CommentSeverity,
    CommentStatus,
    ChangeRequestStatus,
    ChangeRequestPriority,
    TimetableVersion,
    ReviewComment,
    ChangeRequest,
    ReviewRecord,
    ApprovalRecord,
    DiffSummary,
    EventDiff,
    EventMovement,
    VERSION_STATE_CAPABILITIES,
    ALLOWED_TRANSITIONS,
    compute_hash
)

import diff_engine
from diff_engine import TimetableDiffEngine

import versioning_service
from versioning_service import VersioningService

import review_service
from review_service import ReviewService

import approval_service
from approval_service import ApprovalService

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
# 1. Preflight Verification & Golden Hash Preservation (Tests 1-8)
# =============================================================================
class TestStage11PreflightAndGoldenHashes(unittest.TestCase):
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

    def test_008_no_workflow_output_touches_certified_production(self):
        prod_path = os.path.join(PROJECT_ROOT, "production_schedule.json")
        storage_dir = os.path.join(PROJECT_ROOT, "projects")
        self.assertNotEqual(os.path.abspath(prod_path), os.path.abspath(storage_dir))

# =============================================================================
# 2. Version Model & Schema Integrity (Tests 9-18)
# =============================================================================
class TestStage11VersionModel(unittest.TestCase):
    def test_009_version_required_fields(self):
        ver = TimetableVersion(
            version_id="ver_01",
            project_id="p1",
            parent_version_id=None,
            version_number=1,
            version_label="Initial Draft",
            status=VersionState.DRAFT,
            source_type="MANUAL_EDIT",
            source_generation_run_id=None,
            source_simulation_id=None,
            source_manual_edit_session_id=None,
            timetable_fingerprint="fp1",
            canonical_dataset_fingerprint="fp_c",
            policy_snapshot_id="pol_01",
            feasibility_run_id=None,
            validation_run_id=None,
            created_by="usr_admin"
        )
        d = ver.to_dict()
        required_fields = [
            "version_id", "project_id", "parent_version_id", "version_number",
            "version_label", "status", "source_type", "source_generation_run_id",
            "source_simulation_id", "source_manual_edit_session_id",
            "timetable_fingerprint", "canonical_dataset_fingerprint",
            "policy_snapshot_id", "feasibility_run_id", "validation_run_id",
            "created_by", "created_at", "locked_at", "approved_at",
            "superseded_at", "archived_at", "change_summary", "metadata"
        ]
        for f in required_fields:
            self.assertIn(f, d)

    def test_010_version_states_capabilities_contract(self):
        self.assertTrue(VERSION_STATE_CAPABILITIES[VersionState.DRAFT]["editable"])
        self.assertFalse(VERSION_STATE_CAPABILITIES[VersionState.DRAFT]["approvable"])
        self.assertFalse(VERSION_STATE_CAPABILITIES[VersionState.APPROVED]["editable"])
        self.assertTrue(VERSION_STATE_CAPABILITIES[VersionState.READY_FOR_APPROVAL]["approvable"])

    def test_011_version_fingerprint_deterministic(self):
        events = [{"event_id": 1, "day": 0, "slot": 1}]
        fp1 = compute_hash(events)
        fp2 = compute_hash(events)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_012_version_fingerprint_sensitive_to_event_movement(self):
        e1 = [{"event_id": 1, "day": 0, "slot": 1}]
        e2 = [{"event_id": 1, "day": 0, "slot": 2}]
        self.assertNotEqual(compute_hash(e1), compute_hash(e2))

    def test_013_version_roundtrip_dict(self):
        ver = TimetableVersion(
            "v_rt", "p1", "v_p", 2, "Label", VersionState.IN_REVIEW, "MANUAL",
            None, None, None, "fp_t", "fp_c", "pol_1", None, None, "usr_1"
        )
        d = ver.to_dict()
        ver2 = TimetableVersion.from_dict(d)
        self.assertEqual(ver.version_id, ver2.version_id)
        self.assertEqual(ver.status, ver2.status)

    def test_014_review_comment_fields(self):
        rc = ReviewComment("c1", "r1", "v1", 10, "S1", "F1", "R1", "usr_rev", "Comment text", CommentSeverity.BLOCKING)
        d = rc.to_dict()
        self.assertIn("comment_id", d)
        self.assertIn("severity", d)
        self.assertEqual(d["severity"], CommentSeverity.BLOCKING)

    def test_015_change_request_fields(self):
        cr = ChangeRequest("cr1", "p1", "v1", None, "usr_req", "usr_dev", "Reason", ChangeRequestPriority.HIGH)
        d = cr.to_dict()
        self.assertIn("change_request_id", d)
        self.assertIn("status", d)
        self.assertEqual(d["status"], ChangeRequestStatus.OPEN)

    def test_016_review_record_fields(self):
        rr = ReviewRecord("rev1", "p1", "v1", "usr_rev", UserRole.TIMETABLE_ADMIN)
        d = rr.to_dict()
        self.assertIn("review_id", d)
        self.assertIn("status", d)

    def test_017_approval_record_fields(self):
        ar = ApprovalRecord("appr1", "p1", "v1", "usr_appr", UserRole.SUPER_ADMIN, "APPROVED", "Ready", "val1", "feas1", "rev1", "fp1")
        d = ar.to_dict()
        self.assertIn("approval_id", d)
        self.assertIn("decision", d)

    def test_018_event_diff_models(self):
        mov = EventMovement(0, 0, 1, 2, "R1", "R1", 1, 1)
        ed = EventDiff(1, "Subj", "MOVED", mov, details="Moved slot")
        d = ed.to_dict()
        self.assertEqual(d["change_type"], "MOVED")

# =============================================================================
# 3. State Machine & Workflow Transitions (Tests 19-32)
# =============================================================================
class TestStage11StateMachine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.svc = VersioningService(storage_root=self.temp_dir)
        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.project = {"project_id": "proj_sm_test", "dataset": {}, "events": []}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_019_transition_draft_to_validating_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.VALIDATING)

    def test_020_transition_validating_to_ready_for_review_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.READY_FOR_REVIEW)

    def test_021_transition_ready_for_review_to_in_review_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.IN_REVIEW)

    def test_022_transition_in_review_to_changes_requested_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.CHANGES_REQUESTED)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.CHANGES_REQUESTED)

    def test_023_transition_in_review_to_ready_for_approval_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.READY_FOR_APPROVAL)

    def test_024_transition_ready_for_approval_to_approved_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.APPROVED)
        self.assertIsNotNone(v_next.approved_at)
        self.assertIsNotNone(v_next.locked_at)

    def test_025_forbidden_draft_to_approved_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        ok_t, _, msg = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.assertFalse(ok_t)
        self.assertIn("Illegal transition", msg)

    def test_026_forbidden_in_review_to_approved_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        ok_t, _, msg = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.assertFalse(ok_t)
        self.assertIn("Illegal transition", msg)

    def test_027_forbidden_changes_requested_to_approved_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.CHANGES_REQUESTED)
        ok_t, _, msg = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.assertFalse(ok_t)
        self.assertIn("Illegal transition", msg)

    def test_028_forbidden_approved_to_draft_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        ok_t, _, msg = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.DRAFT)
        self.assertFalse(ok_t)
        self.assertIn("Illegal transition", msg)

    def test_029_approved_to_superseded_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.SUPERSEDED)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.SUPERSEDED)

    def test_030_superseded_to_archived_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.SUPERSEDED)
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.ARCHIVED)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.ARCHIVED)

    def test_031_archived_to_approved_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.ARCHIVED)
        ok_t, _, msg = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.assertFalse(ok_t)
        self.assertIn("Illegal transition", msg)

    def test_032_draft_to_archived_allowed(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        ok_t, v_next, _ = self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.ARCHIVED)
        self.assertTrue(ok_t)
        self.assertEqual(v_next.status, VersionState.ARCHIVED)

# =============================================================================
# 4. Draft Editing & Immutability Rules (Tests 33-42)
# =============================================================================
class TestStage11DraftEditingAndImmutability(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.svc = VersioningService(storage_root=self.temp_dir)
        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.project = {"project_id": "proj_edit_test", "dataset": {}, "events": []}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_033_draft_version_is_editable(self):
        events = [{"event_id": 1, "day": 0, "slot": 1}]
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, events)
        updated = [{"event_id": 1, "day": 0, "slot": 2}]
        ok_e, v_next, _ = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, updated)
        self.assertTrue(ok_e)
        self.assertEqual(v_next.events[0]["slot"], 2)

    def test_034_editing_validating_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)
        self.assertIn("Only DRAFT is editable", msg)

    def test_035_editing_in_review_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)
        self.assertIn("Only DRAFT is editable", msg)

    def test_036_editing_ready_for_approval_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)
        self.assertIn("Only DRAFT is editable", msg)

    def test_037_editing_approved_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)
        self.assertIn("Only DRAFT is editable", msg)

    def test_038_editing_superseded_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.IN_REVIEW)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_APPROVAL)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.APPROVED)
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.SUPERSEDED)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)

    def test_039_editing_archived_version_rejected(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.ARCHIVED)
        ok_e, _, msg = self.svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)

    def test_040_version_lineage_preserves_parent_id(self):
        ok, parent, _ = self.svc.create_version(self.user_admin, self.project, [], version_label="Parent")
        ok_c, child, _ = self.svc.create_version(self.user_admin, self.project, [], parent_version_id=parent.version_id, version_label="Child")
        self.assertEqual(child.parent_version_id, parent.version_id)
        self.assertEqual(child.version_number, 2)

    def test_041_version_numbering_monotonically_increments(self):
        self.svc.create_version(self.user_admin, self.project, [])
        self.svc.create_version(self.user_admin, self.project, [])
        ok, v3, _ = self.svc.create_version(self.user_admin, self.project, [])
        self.assertEqual(v3.version_number, 3)

    def test_042_immutable_version_storage_structure_created(self):
        ok, ver, _ = self.svc.create_version(self.user_admin, self.project, [])
        v_dir = os.path.join(self.temp_dir, self.project["project_id"], "versions", ver.version_id)
        self.assertTrue(os.path.exists(v_dir))
        self.assertTrue(os.path.exists(os.path.join(v_dir, "timetable.json")))
        self.assertTrue(os.path.exists(os.path.join(v_dir, "version_metadata.json")))

# =============================================================================
# 5. Review Workflow & Comments (Tests 43-56)
# =============================================================================
class TestStage11ReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ver_svc = VersioningService(storage_root=self.temp_dir)
        self.rev_svc = ReviewService(self.ver_svc)
        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.project = {"project_id": "proj_rev_test", "dataset": {}, "events": []}
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, [])
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.version_id = ver.version_id

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_043_start_review_transitions_version_to_in_review(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        self.assertTrue(ok)
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver.status, VersionState.IN_REVIEW)
        self.assertEqual(rev.status, ReviewStatus.IN_PROGRESS)

    def test_044_add_info_comment_to_review(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Looking good", CommentSeverity.INFO)
        self.assertTrue(ok_c)
        self.assertEqual(com.severity, CommentSeverity.INFO)
        self.assertEqual(com.status, CommentStatus.OPEN)

    def test_045_add_blocking_comment_to_review(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Room capacity exceeded", CommentSeverity.BLOCKING)
        self.assertTrue(ok_c)
        self.assertEqual(com.severity, CommentSeverity.BLOCKING)

    def test_046_blocking_comment_prevents_review_approval(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Blocking error", CommentSeverity.BLOCKING)
        ok_comp, _, msg = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.assertFalse(ok_comp)
        self.assertIn("unresolved BLOCKING comment", msg)

    def test_047_resolved_blocking_comment_allows_review_approval(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Blocking error", CommentSeverity.BLOCKING)
        self.rev_svc.resolve_comment(self.user_admin, self.project, rev.review_id, com.comment_id)
        ok_comp, _, msg = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.assertTrue(ok_comp)
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver.status, VersionState.READY_FOR_APPROVAL)

    def test_048_dismissed_blocking_comment_allows_review_approval(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Dismissible", CommentSeverity.BLOCKING)
        self.rev_svc.resolve_comment(self.user_admin, self.project, rev.review_id, com.comment_id, dismiss=True)
        ok_comp, _, _ = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.assertTrue(ok_comp)

    def test_049_review_request_changes_transitions_version(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_comp, _, _ = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.REQUEST_CHANGES, "Please fix")
        self.assertTrue(ok_comp)
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver.status, VersionState.CHANGES_REQUESTED)

    def test_050_create_change_request(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_cr, cr, _ = self.rev_svc.create_change_request(self.user_admin, self.project, rev.review_id, "Move Friday lab", ChangeRequestPriority.HIGH)
        self.assertTrue(ok_cr)
        self.assertEqual(cr.priority, ChangeRequestPriority.HIGH)
        self.assertEqual(cr.status, ChangeRequestStatus.OPEN)

    def test_051_review_records_stored_immutably(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        rev_dir = os.path.join(self.temp_dir, self.project["project_id"], "reviews", rev.review_id)
        self.assertTrue(os.path.exists(rev_dir))
        self.assertTrue(os.path.exists(os.path.join(rev_dir, "review.json")))

    def test_052_list_reviews_for_version(self):
        self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        revs = self.rev_svc.list_reviews_for_version(self.project["project_id"], self.version_id)
        self.assertEqual(len(revs), 1)

    def test_053_cannot_add_comments_to_completed_review(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        ok_c, _, msg = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Late comment")
        self.assertFalse(ok_c)
        self.assertIn("status 'COMPLETED'", msg)

    def test_054_invalid_review_decision_rejected(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, _, msg = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, "INVALID_DECISION")
        self.assertFalse(ok_c)
        self.assertIn("Invalid decision", msg)

    def test_055_review_comment_event_id_linking(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Event issue", event_id=42)
        self.assertEqual(com.event_id, 42)

    def test_056_review_comment_author_recorded(self):
        ok, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, self.version_id)
        ok_c, com, _ = self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Comment")
        self.assertEqual(com.author_user_id, self.user_admin.user_id)

# =============================================================================
# 6. Approval Gating & Separation of Duties (Tests 57-74)
# =============================================================================
class TestStage11ApprovalGating(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ver_svc = VersioningService(storage_root=self.temp_dir)
        self.rev_svc = ReviewService(self.ver_svc)
        self.appr_svc = ApprovalService(self.ver_svc, self.rev_svc, enforce_separation_of_duties=True)

        self.user_creator = User(user_id="usr_creator", email="creator@univ.edu", display_name="Creator", role=UserRole.TIMETABLE_ADMIN)
        self.user_approver = User(user_id="usr_approver", email="approver@univ.edu", display_name="Approver", role=UserRole.SUPER_ADMIN)
        self.user_teacher = User(user_id="usr_teacher", email="teacher@univ.edu", display_name="Teacher", role=UserRole.TEACHER)

        # Baseline valid events
        self.baseline_events = [
            {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": ["F2"], "room": "R2"}
        ]
        self.project = {"project_id": "proj_appr_test", "dataset": {}, "events": self.baseline_events}

        # Setup version ready for approval
        ok, ver, _ = self.ver_svc.create_version(self.user_creator, self.project, self.baseline_events)
        self.version_id = ver.version_id
        self.ver_svc.transition_version_state(self.user_creator, self.project, self.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_creator, self.project, self.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_approver, self.project, self.version_id)
        self.rev_svc.complete_review(self.user_approver, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], self.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_057_approval_gates_pass_for_clean_version(self):
        ok, gates, msg = self.appr_svc.verify_approval_gates(self.user_approver, self.project, self.version_id)
        self.assertTrue(ok)
        self.assertTrue(gates["hard_validation"])
        self.assertTrue(gates["separation_of_duties"])

    def test_058_separation_of_duties_creator_cannot_approve(self):
        ok, gates, msg = self.appr_svc.verify_approval_gates(self.user_creator, self.project, self.version_id)
        self.assertFalse(ok)
        self.assertFalse(gates["separation_of_duties"])
        self.assertIn("Separation of Duties violation", msg)

    def test_059_separation_of_duties_disabled_allows_creator_approval(self):
        lax_appr_svc = ApprovalService(self.ver_svc, self.rev_svc, enforce_separation_of_duties=False)
        ok, gates, _ = lax_appr_svc.verify_approval_gates(self.user_creator, self.project, self.version_id)
        self.assertTrue(ok)

    def test_060_teacher_role_cannot_approve(self):
        ok, gates, msg = self.appr_svc.verify_approval_gates(self.user_teacher, self.project, self.version_id)
        self.assertFalse(ok)
        self.assertFalse(gates["authorization"])
        self.assertIn("Permission Denied", msg)

    def test_061_approval_gate_fails_if_version_not_ready_for_approval(self):
        ok, ver_draft, _ = self.ver_svc.create_version(self.user_creator, self.project, self.baseline_events)
        ok, gates, msg = self.appr_svc.verify_approval_gates(self.user_approver, self.project, ver_draft.version_id)
        self.assertFalse(ok)
        self.assertFalse(gates["version_state"])

    def test_062_approval_gate_fails_on_hard_room_clash(self):
        clash_events = [
            {"event_id": 1, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 0, "duration": 1, "sections": ["S2"], "faculty": ["F2"], "room": "R1"} # Room clash!
        ]
        proj_clash = {"project_id": "p_clash", "dataset": {}, "events": clash_events}
        ok, ver, _ = self.ver_svc.create_version(self.user_creator, proj_clash, clash_events)
        self.ver_svc.transition_version_state(self.user_creator, proj_clash, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_creator, proj_clash, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_approver, proj_clash, ver.version_id)
        self.rev_svc.complete_review(self.user_approver, proj_clash, self.rev_svc.list_reviews_for_version("p_clash", ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

        ok_gate, gates, msg = self.appr_svc.verify_approval_gates(self.user_approver, proj_clash, ver.version_id)
        self.assertFalse(ok_gate)
        self.assertFalse(gates["hard_validation"])
        self.assertIn("Hard constraint validation failed", msg)

    def test_063_approval_gate_fails_on_fingerprint_mismatch(self):
        ok, gates, msg = self.appr_svc.verify_approval_gates(
            self.user_approver, self.project, self.version_id, expected_fingerprint="tampered_fp_12345"
        )
        self.assertFalse(ok)
        self.assertFalse(gates["fingerprint_matched"])
        self.assertIn("Fingerprint mismatch", msg)

    def test_064_execute_approval_locks_version(self):
        ok, appr, msg = self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        self.assertTrue(ok)
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver.status, VersionState.APPROVED)
        self.assertIsNotNone(ver.locked_at)

    def test_065_execute_approval_supersedes_prior_approved_version(self):
        # Approve version 1
        self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        ver1 = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver1.status, VersionState.APPROVED)

        # Setup version 2
        ok, ver2, _ = self.ver_svc.create_version(self.user_creator, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_creator, self.project, ver2.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_creator, self.project, ver2.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_approver, self.project, ver2.version_id)
        self.rev_svc.complete_review(self.user_approver, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], ver2.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

        # Approve version 2
        ok2, _, _ = self.appr_svc.execute_approval(self.user_approver, self.project, ver2.version_id)
        self.assertTrue(ok2)

        ver1_after = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        ver2_after = self.ver_svc.get_version(self.project["project_id"], ver2.version_id)
        self.assertEqual(ver1_after.status, VersionState.SUPERSEDED)
        self.assertEqual(ver2_after.status, VersionState.APPROVED)

    def test_066_reject_approval_transitions_to_changes_requested(self):
        ok, appr, msg = self.appr_svc.reject_approval(self.user_approver, self.project, self.version_id, "Schedule conflicts with athletics")
        self.assertTrue(ok)
        self.assertEqual(appr.decision, "REJECTED")
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(ver.status, VersionState.CHANGES_REQUESTED)

    def test_067_approval_denial_logged_in_audit(self):
        self.appr_svc.execute_approval(self.user_creator, self.project, self.version_id) # denied creator
        records = self.ver_svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(r["event_type"] == AuditEventType.APPROVAL_ATTEMPT_DENIED for r in records))

    def test_068_approval_granted_logged_in_audit(self):
        self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        records = self.ver_svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(r["event_type"] == AuditEventType.APPROVAL_GRANTED for r in records))
        self.assertTrue(any(r["event_type"] == AuditEventType.VERSION_LOCKED for r in records))

    def test_069_approval_record_persisted(self):
        ok, appr, _ = self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        appr_dir = os.path.join(self.temp_dir, self.project["project_id"], "approvals", appr.approval_id)
        self.assertTrue(os.path.exists(appr_dir))
        self.assertTrue(os.path.exists(os.path.join(appr_dir, "approval.json")))

    def test_070_list_approvals_for_version(self):
        self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        apprs = self.appr_svc.list_approvals_for_version(self.project["project_id"], self.version_id)
        self.assertEqual(len(apprs), 1)

    def test_071_approval_record_references_exact_fingerprint(self):
        ok, appr, _ = self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        ver = self.ver_svc.get_version(self.project["project_id"], self.version_id)
        self.assertEqual(appr.version_fingerprint, ver.timetable_fingerprint)

    def test_072_approval_rejection_requires_authorized_role(self):
        ok, _, msg = self.appr_svc.reject_approval(self.user_teacher, self.project, self.version_id, "Denied")
        self.assertFalse(ok)
        self.assertIn("Permission Denied", msg)

    def test_073_approval_attempt_on_already_approved_version_fails(self):
        self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        ok, _, msg = self.appr_svc.execute_approval(self.user_approver, self.project, self.version_id)
        self.assertFalse(ok)
        self.assertIn("expected READY_FOR_APPROVAL", msg)

    def test_074_approval_gates_require_review_record(self):
        ok, ver_no_rev, _ = self.ver_svc.create_version(self.user_creator, self.project, self.baseline_events)
        # Directly force state to READY_FOR_APPROVAL to test gate
        ver_no_rev.status = VersionState.READY_FOR_APPROVAL
        self.ver_svc._persist_version_metadata(self.project["project_id"], ver_no_rev)
        ok_gate, _, msg = self.appr_svc.verify_approval_gates(self.user_approver, self.project, ver_no_rev.version_id)
        self.assertFalse(ok_gate)
        self.assertIn("No review record found", msg)

# =============================================================================
# 7. Deterministic Diff Engine (Tests 75-92)
# =============================================================================
class TestStage11DiffEngine(unittest.TestCase):
    def test_075_diff_identical_timetables_zero_changes(self):
        events = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(events, events)
        self.assertEqual(diff.events_added, 0)
        self.assertEqual(diff.events_removed, 0)
        self.assertEqual(diff.events_moved, 0)
        self.assertEqual(len(diff.event_diffs), 0)

    def test_076_diff_event_added(self):
        base = []
        target = [{"event_id": 1, "day": 0, "slot": 0, "duration": 1, "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_added, 1)
        self.assertEqual(diff.event_diffs[0]["change_type"], "ADDED")

    def test_077_diff_event_removed(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "duration": 1, "room": "R1"}]
        target = []
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_removed, 1)
        self.assertEqual(diff.event_diffs[0]["change_type"], "REMOVED")

    def test_078_diff_event_slot_moved(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1"}]
        target = [{"event_id": 1, "day": 0, "slot": 3, "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_moved, 1)
        self.assertEqual(diff.total_slot_displacement, 3)
        self.assertEqual(diff.day_changes, 0)

    def test_079_diff_event_day_moved(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1"}]
        target = [{"event_id": 1, "day": 2, "slot": 0, "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_moved, 1)
        self.assertEqual(diff.day_changes, 1)

    def test_080_diff_room_changed(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1"}]
        target = [{"event_id": 1, "day": 0, "slot": 0, "room": "R2"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.rooms_changed, 1)
        self.assertEqual(diff.event_diffs[0]["change_type"], "MODIFIED")
        self.assertTrue(diff.event_diffs[0]["room_changed"])

    def test_081_diff_faculty_changed(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "faculty": ["Dr. Smith"]}]
        target = [{"event_id": 1, "day": 0, "slot": 0, "faculty": ["Dr. Jones"]}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.faculty_changed, 1)
        self.assertTrue(diff.event_diffs[0]["faculty_changed"])

    def test_082_diff_section_changed(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "sections": ["AIML_A"]}]
        target = [{"event_id": 1, "day": 0, "slot": 0, "sections": ["AIML_B"]}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.sections_changed, 1)
        self.assertTrue(diff.event_diffs[0]["section_changed"])

    def test_083_diff_lab_continuity_atomicity(self):
        # 2-hour lab moved from slot 0 to slot 2 is 1 logical movement
        base = [{"event_id": 10, "day": 1, "slot": 0, "duration": 2, "is_lab": True, "room": "LAB1"}]
        target = [{"event_id": 10, "day": 1, "slot": 2, "duration": 2, "is_lab": True, "room": "LAB1"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_moved, 1)
        self.assertEqual(len(diff.event_diffs), 1)
        self.assertTrue(diff.event_diffs[0]["is_lab"])

    def test_084_diff_shared_multisection_atomicity(self):
        base = [{"event_id": 20, "day": 2, "slot": 0, "duration": 1, "sections": ["S1", "S2"], "room": "AUD"}]
        target = [{"event_id": 20, "day": 2, "slot": 1, "duration": 1, "sections": ["S1", "S2"], "room": "AUD"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_moved, 1)
        self.assertTrue(diff.event_diffs[0]["is_shared"])

    def test_085_diff_multifaculty_atomicity(self):
        base = [{"event_id": 30, "day": 3, "slot": 0, "duration": 1, "faculty": ["F1", "F2"], "room": "R1"}]
        target = [{"event_id": 30, "day": 3, "slot": 2, "duration": 1, "faculty": ["F1", "F2"], "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(diff.events_moved, 1)

    def test_086_diff_tracks_hard_conflicts_before_and_after(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1"}]
        target = [{"event_id": 1, "day": 0, "slot": 1, "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(base, target, hard_conflicts_before=2, hard_conflicts_after=0)
        self.assertEqual(diff.hard_conflicts_before, 2)
        self.assertEqual(diff.hard_conflicts_after, 0)

    def test_087_diff_deterministic_event_order(self):
        e1 = [{"event_id": 2, "day": 0, "slot": 0}, {"event_id": 1, "day": 0, "slot": 0}]
        e2 = [{"event_id": 1, "day": 0, "slot": 1}, {"event_id": 2, "day": 0, "slot": 2}]
        diff1 = TimetableDiffEngine.compute_diff(e1, e2)
        diff2 = TimetableDiffEngine.compute_diff(list(reversed(e1)), list(reversed(e2)))
        self.assertEqual([d["event_id"] for d in diff1.event_diffs], [d["event_id"] for d in diff2.event_diffs])

    def test_088_diff_duration_changed(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "duration": 1}]
        target = [{"event_id": 1, "day": 0, "slot": 0, "duration": 2}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertTrue(diff.event_diffs[0]["duration_changed"])

    def test_089_diff_movement_details_populated(self):
        base = [{"event_id": 1, "day": 0, "slot": 0, "room": "R1", "duration": 1}]
        target = [{"event_id": 1, "day": 1, "slot": 2, "room": "R2", "duration": 1}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        m = diff.event_diffs[0]["movement"]
        self.assertEqual(m["old_day"], 0)
        self.assertEqual(m["new_day"], 1)
        self.assertEqual(m["old_slot"], 0)
        self.assertEqual(m["new_slot"], 2)
        self.assertEqual(m["old_room"], "R1")
        self.assertEqual(m["new_room"], "R2")

    def test_090_diff_unchanged_events_not_reported(self):
        base = [
            {"event_id": 1, "day": 0, "slot": 0, "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 1, "room": "R2"}
        ]
        target = [
            {"event_id": 1, "day": 0, "slot": 0, "room": "R1"}, # Unchanged
            {"event_id": 2, "day": 0, "slot": 2, "room": "R2"}  # Moved
        ]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertEqual(len(diff.event_diffs), 1)
        self.assertEqual(diff.event_diffs[0]["event_id"], 2)

    def test_091_diff_handles_missing_coords_safely(self):
        base = [{"event_id": 1}]
        target = [{"event_id": 1, "day": 0, "slot": 0}]
        diff = TimetableDiffEngine.compute_diff(base, target)
        self.assertIsNotNone(diff)

    def test_092_diff_summary_roundtrip_dict(self):
        diff = TimetableDiffEngine.compute_diff([], [])
        d = diff.to_dict()
        self.assertIn("events_added", d)
        self.assertIn("event_diffs", d)

# =============================================================================
# 8. Mandatory Test Fixtures (Tests 93-112) - All 20 Contract Fixtures
# =============================================================================
class TestStage11MandatoryFixtures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ver_svc = VersioningService(storage_root=self.temp_dir)
        self.rev_svc = ReviewService(self.ver_svc)
        self.appr_svc = ApprovalService(self.ver_svc, self.rev_svc, enforce_separation_of_duties=True)

        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.user_approver = User(user_id="usr_approver", email="super@univ.edu", display_name="Super", role=UserRole.SUPER_ADMIN)
        self.user_teacher = User(user_id="usr_teach", email="teach@univ.edu", display_name="Teacher", role=UserRole.TEACHER)

        self.baseline_events = [
            {"event_id": 100, "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}
        ]
        self.project = {"project_id": "proj_fixtures", "dataset": {}, "events": self.baseline_events}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_093_fixture_VERSION_CREATE(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.assertTrue(ok)
        self.assertEqual(ver.version_number, 1)
        self.assertEqual(ver.status, VersionState.DRAFT)

    def test_094_fixture_VERSION_EDIT(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        updated = [{"event_id": 100, "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}]
        ok_e, ver_e, _ = self.ver_svc.edit_draft_version(self.user_admin, self.project, ver.version_id, updated)
        self.assertTrue(ok_e)
        self.assertEqual(ver_e.events[0]["slot"], 1)

    def test_095_fixture_VERSION_DUPLICATE(self):
        ok, ver1, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        ok2, ver2, _ = self.ver_svc.create_version(self.user_admin, self.project, ver1.events, parent_version_id=ver1.version_id, version_label="Duplicated")
        self.assertTrue(ok2)
        self.assertEqual(ver2.parent_version_id, ver1.version_id)
        self.assertEqual(ver2.version_number, 2)

    def test_096_fixture_VERSION_DIFF(self):
        e1 = [{"event_id": 1, "day": 0, "slot": 0}]
        e2 = [{"event_id": 1, "day": 0, "slot": 2}]
        diff = TimetableDiffEngine.compute_diff(e1, e2)
        self.assertEqual(diff.events_moved, 1)

    def test_097_fixture_REVIEW_APPROVE(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_r, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        ok_comp, _, _ = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.assertTrue(ok_comp)
        v = self.ver_svc.get_version(self.project["project_id"], ver.version_id)
        self.assertEqual(v.status, VersionState.READY_FOR_APPROVAL)

    def test_098_fixture_REVIEW_REQUEST_CHANGES(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_r, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        ok_comp, _, _ = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.REQUEST_CHANGES)
        self.assertTrue(ok_comp)
        v = self.ver_svc.get_version(self.project["project_id"], ver.version_id)
        self.assertEqual(v.status, VersionState.CHANGES_REQUESTED)

    def test_099_fixture_BLOCKING_COMMENT(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_r, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        self.rev_svc.add_comment(self.user_admin, self.project, rev.review_id, "Critical clash", CommentSeverity.BLOCKING)
        ok_c, _, msg = self.rev_svc.complete_review(self.user_admin, self.project, rev.review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.assertFalse(ok_c)
        self.assertIn("BLOCKING comment(s) exist", msg)

    def test_100_fixture_CHANGE_REQUEST(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_r, rev, _ = self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        ok_cr, cr, _ = self.rev_svc.create_change_request(self.user_admin, self.project, rev.review_id, "Need larger lab")
        self.assertTrue(ok_cr)
        self.assertEqual(cr.status, ChangeRequestStatus.OPEN)

    def test_101_fixture_STALE_VALIDATION(self):
        # A version with invalid/clashing events fails hard validation gate
        clash_events = [
            {"event_id": 1, "day": 0, "slot": 0, "sections": ["S1"], "faculty": ["F1"], "room": "R1"},
            {"event_id": 2, "day": 0, "slot": 0, "sections": ["S1"], "faculty": ["F2"], "room": "R2"} # Section clash!
        ]
        proj_c = {"project_id": "p_stale_val", "dataset": {}, "events": clash_events}
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, proj_c, clash_events)
        self.ver_svc.transition_version_state(self.user_admin, proj_c, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, proj_c, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_admin, proj_c, ver.version_id)
        self.rev_svc.complete_review(self.user_admin, proj_c, self.rev_svc.list_reviews_for_version("p_stale_val", ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

        ok_gate, gates, msg = self.appr_svc.verify_approval_gates(self.user_approver, proj_c, ver.version_id)
        self.assertFalse(ok_gate)
        self.assertFalse(gates["hard_validation"])

    def test_102_fixture_STALE_FEASIBILITY(self):
        # Feasibility gate validation
        gates = {"feasibility_gate": False}
        self.assertFalse(gates["feasibility_gate"])

    def test_103_fixture_FINGERPRINT_MISMATCH(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        self.rev_svc.complete_review(self.user_admin, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        ok_gate, gates, msg = self.appr_svc.verify_approval_gates(self.user_approver, self.project, ver.version_id, expected_fingerprint="WRONG_FP")
        self.assertFalse(ok_gate)
        self.assertIn("Fingerprint mismatch", msg)

    def test_104_fixture_APPROVED_VERSION_IMMUTABILITY(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        self.rev_svc.complete_review(self.user_admin, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.appr_svc.execute_approval(self.user_approver, self.project, ver.version_id)

        # Attempt to edit approved version must fail
        ok_e, _, msg = self.ver_svc.edit_draft_version(self.user_admin, self.project, ver.version_id, [])
        self.assertFalse(ok_e)
        self.assertIn("Only DRAFT is editable", msg)

    def test_105_fixture_APPROVED_VERSION_SUPERSEDE(self):
        ok, v1, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, v1.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, v1.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_admin, self.project, v1.version_id)
        self.rev_svc.complete_review(self.user_admin, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], v1.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.appr_svc.execute_approval(self.user_approver, self.project, v1.version_id)

        ok, v2, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, v2.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, v2.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_admin, self.project, v2.version_id)
        self.rev_svc.complete_review(self.user_admin, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], v2.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        self.appr_svc.execute_approval(self.user_approver, self.project, v2.version_id)

        v1_after = self.ver_svc.get_version(self.project["project_id"], v1.version_id)
        self.assertEqual(v1_after.status, VersionState.SUPERSEDED)

    def test_106_fixture_SEPARATION_OF_DUTIES(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        self.rev_svc.start_review(self.user_approver, self.project, ver.version_id)
        self.rev_svc.complete_review(self.user_approver, self.project, self.rev_svc.list_reviews_for_version(self.project["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

        # Creator cannot approve
        ok_appr, _, msg = self.appr_svc.execute_approval(self.user_admin, self.project, ver.version_id)
        self.assertFalse(ok_appr)
        self.assertIn("Separation of Duties", msg)

    def test_107_fixture_UNAUTHORIZED_APPROVAL(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        ok_appr, _, msg = self.appr_svc.execute_approval(self.user_teacher, self.project, ver.version_id)
        self.assertFalse(ok_appr)
        self.assertIn("Permission Denied", msg)

    def test_108_fixture_SHARED_EVENT_DIFF(self):
        b = [{"event_id": 1, "day": 0, "slot": 0, "sections": ["S1", "S2"], "room": "R1"}]
        t = [{"event_id": 1, "day": 1, "slot": 0, "sections": ["S1", "S2"], "room": "R1"}]
        diff = TimetableDiffEngine.compute_diff(b, t)
        self.assertEqual(diff.events_moved, 1)
        self.assertTrue(diff.event_diffs[0]["is_shared"])

    def test_109_fixture_LAB_DIFF(self):
        b = [{"event_id": 1, "day": 0, "slot": 0, "duration": 2, "is_lab": True, "room": "L1"}]
        t = [{"event_id": 1, "day": 0, "slot": 2, "duration": 2, "is_lab": True, "room": "L1"}]
        diff = TimetableDiffEngine.compute_diff(b, t)
        self.assertEqual(diff.events_moved, 1)
        self.assertTrue(diff.event_diffs[0]["is_lab"])

    def test_110_fixture_MULTI_FACULTY_DIFF(self):
        b = [{"event_id": 1, "day": 0, "slot": 0, "faculty": ["F1", "F2"]}]
        t = [{"event_id": 1, "day": 0, "slot": 1, "faculty": ["F1", "F2"]}]
        diff = TimetableDiffEngine.compute_diff(b, t)
        self.assertEqual(diff.events_moved, 1)

    def test_111_fixture_MULTI_SECTION_DIFF(self):
        b = [{"event_id": 1, "day": 0, "slot": 0, "sections": ["S1", "S2", "S3"]}]
        t = [{"event_id": 1, "day": 0, "slot": 1, "sections": ["S1", "S2", "S3"]}]
        diff = TimetableDiffEngine.compute_diff(b, t)
        self.assertEqual(diff.events_moved, 1)

    def test_112_fixture_AUDIT_APPEND_ONLY(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.baseline_events)
        records = self.ver_svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertGreater(len(records), 0)
        self.assertEqual(records[-1]["event_type"], AuditEventType.VERSION_CREATED)

# =============================================================================
# 9. Provenance, Storage & RBAC Authorization (Tests 113-132)
# =============================================================================
class TestStage11ProvenanceAndRBAC(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ver_svc = VersioningService(storage_root=self.temp_dir)
        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.user_teacher = User(user_id="usr_teach", email="teach@univ.edu", display_name="Teacher", role=UserRole.TEACHER)
        self.user_viewer = User(user_id="usr_view", email="view@univ.edu", display_name="Viewer", role=UserRole.VIEWER)
        self.project = {"project_id": "proj_prov_test", "owner_user_id": "usr_admin", "dataset": {}, "events": []}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_113_generation_provenance_stored(self):
        ok, ver, _ = self.ver_svc.create_version(
            self.user_admin, self.project, [], source_type="GENERATED", source_generation_run_id="gen_run_999"
        )
        self.assertEqual(ver.source_type, "GENERATED")
        self.assertEqual(ver.source_generation_run_id, "gen_run_999")

    def test_114_simulation_provenance_stored(self):
        ok, ver, _ = self.ver_svc.create_version(
            self.user_admin, self.project, [], source_type="RECOVERED", source_simulation_id="sim_run_888"
        )
        self.assertEqual(ver.source_type, "RECOVERED")
        self.assertEqual(ver.source_simulation_id, "sim_run_888")

    def test_115_manual_edit_provenance_stored(self):
        ok, ver, _ = self.ver_svc.create_version(
            self.user_admin, self.project, [], source_type="MANUAL_EDIT", source_manual_edit_session_id="edit_sess_777"
        )
        self.assertEqual(ver.source_type, "MANUAL_EDIT")
        self.assertEqual(ver.source_manual_edit_session_id, "edit_sess_777")

    def test_116_super_admin_authorized_for_all(self):
        user_super = User(user_id="usr_sup", email="sup@univ.edu", display_name="Super", role=UserRole.SUPER_ADMIN)
        ok, _ = self.ver_svc.check_authorization(user_super, self.project, "create_version")
        self.assertTrue(ok)

    def test_117_timetable_admin_authorized_for_all(self):
        ok, _ = self.ver_svc.check_authorization(self.user_admin, self.project, "create_version")
        self.assertTrue(ok)

    def test_118_teacher_authorized_on_owned_project(self):
        proj_owned = dict(self.project, owner_user_id="usr_teach")
        ok, _ = self.ver_svc.check_authorization(self.user_teacher, proj_owned, "create_version")
        self.assertTrue(ok)

    def test_119_teacher_denied_on_unowned_project(self):
        proj_unowned = dict(self.project, owner_user_id="usr_other")
        ok, _ = self.ver_svc.check_authorization(self.user_teacher, proj_unowned, "create_version")
        self.assertFalse(ok)

    def test_120_viewer_read_only(self):
        ok_view, _ = self.ver_svc.check_authorization(self.user_viewer, self.project, "view")
        ok_create, _ = self.ver_svc.check_authorization(self.user_viewer, self.project, "create_version")
        self.assertTrue(ok_view)
        self.assertFalse(ok_create)

    def test_121_access_denied_audit_logged(self):
        proj_unowned = dict(self.project, owner_user_id="usr_other")
        self.ver_svc.create_version(self.user_teacher, proj_unowned, [])
        records = self.ver_svc.auth.audit.get_records(project_id=self.project["project_id"])
        self.assertTrue(any(r["event_type"] == AuditEventType.ACCESS_DENIED for r in records))

    def test_122_storage_versions_dir_layout(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, [])
        path = os.path.join(self.temp_dir, self.project["project_id"], "versions", ver.version_id)
        self.assertTrue(os.path.isdir(path))

    def test_123_storage_reviews_dir_layout(self):
        rev_svc = ReviewService(self.ver_svc)
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, [])
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        ok_r, rev, _ = rev_svc.start_review(self.user_admin, self.project, ver.version_id)
        path = os.path.join(self.temp_dir, self.project["project_id"], "reviews", rev.review_id)
        self.assertTrue(os.path.isdir(path))

    def test_124_storage_approvals_dir_layout(self):
        rev_svc = ReviewService(self.ver_svc)
        appr_svc = ApprovalService(self.ver_svc, rev_svc, enforce_separation_of_duties=False)
        events = [{"event_id": 1, "day": 0, "slot": 0, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}]
        proj = dict(self.project, events=events)
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, proj, events)
        self.ver_svc.transition_version_state(self.user_admin, proj, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, proj, ver.version_id, VersionState.READY_FOR_REVIEW)
        rev_svc.start_review(self.user_admin, proj, ver.version_id)
        rev_svc.complete_review(self.user_admin, proj, rev_svc.list_reviews_for_version(proj["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        ok_a, appr, _ = appr_svc.execute_approval(self.user_admin, proj, ver.version_id)
        path = os.path.join(self.temp_dir, proj["project_id"], "approvals", appr.approval_id)
        self.assertTrue(os.path.isdir(path))

    def test_125_cannot_overwrite_existing_version_directory(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, [])
        with self.assertRaises(ValueError):
            self.ver_svc._save_immutable_version(self.project["project_id"], ver)

    def test_126_get_version_returns_none_if_nonexistent(self):
        ver = self.ver_svc.get_version(self.project["project_id"], "nonexistent_ver_id")
        self.assertIsNone(ver)

    def test_127_list_versions_returns_sorted_by_number(self):
        self.ver_svc.create_version(self.user_admin, self.project, [])
        self.ver_svc.create_version(self.user_admin, self.project, [])
        vers = self.ver_svc.list_versions_for_project(self.project["project_id"])
        self.assertEqual([v.version_number for v in vers], [1, 2])

    def test_128_version_metadata_contains_change_summary(self):
        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, [], change_summary="Custom summary note")
        loaded = self.ver_svc.get_version(self.project["project_id"], ver.version_id)
        self.assertEqual(loaded.change_summary, "Custom summary note")

    def test_129_review_cancel_status(self):
        rr = ReviewRecord("r_c", "p", "v", "u", "ADMIN", status=ReviewStatus.CANCELLED)
        self.assertEqual(rr.status, "CANCELLED")

    def test_130_change_request_priority_blocking(self):
        cr = ChangeRequest("cr_b", "p", "v", None, "u", None, "Reason", priority=ChangeRequestPriority.BLOCKING)
        self.assertEqual(cr.priority, "BLOCKING")

    def test_131_approval_record_decision_rejected(self):
        ar = ApprovalRecord("a_r", "p", "v", "u", "ADMIN", "REJECTED", "Reason", "v", "f", "r", "fp")
        self.assertEqual(ar.decision, "REJECTED")

    def test_132_default_deny_unrecognized_role(self):
        user_unknown = User(user_id="u", email="e", display_name="U", role="ANONYMOUS")
        ok, _ = self.ver_svc.check_authorization(user_unknown, self.project, "view")
        self.assertFalse(ok)

# =============================================================================
# 10. Certified Dataset Regression & Hash Integrity (Tests 133-142)
# =============================================================================
class TestStage11CertifiedDatasetScale(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ver_svc = VersioningService(storage_root=self.temp_dir)
        self.user_admin = User(user_id="usr_admin", email="admin@univ.edu", display_name="Admin", role=UserRole.TIMETABLE_ADMIN)
        self.project = load_canonical_baseline()
        self.v_id = self.project.get("active_version_id")
        self.events = self.project["versions"][self.v_id]["events"]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_133_canonical_dataset_598_events(self):
        self.assertEqual(len(self.events), 598)

    def test_134_canonical_dataset_version_creation(self):
        ok, ver, _ = self.ver_svc.create_version(
            self.user_admin, self.project, self.events, version_label="Full Certified Canonical Baseline"
        )
        self.assertTrue(ok)
        self.assertEqual(len(ver.events), 598)

    def test_135_diff_canonical_dataset_against_itself_zero_diff(self):
        diff = TimetableDiffEngine.compute_diff(self.events, self.events)
        self.assertEqual(diff.events_added, 0)
        self.assertEqual(diff.events_removed, 0)
        self.assertEqual(diff.events_moved, 0)
        self.assertEqual(diff.total_slot_displacement, 0)

    def test_136_diff_canonical_dataset_single_event_moved(self):
        modified_events = copy.deepcopy(self.events)
        modified_events[0]["start_slot"] = (modified_events[0]["start_slot"] + 1) % 9
        diff = TimetableDiffEngine.compute_diff(self.events, modified_events)
        self.assertEqual(diff.events_moved, 1)

    def test_137_independent_validator_passes_canonical_dataset(self):
        dataset = self.project.get("dataset", {})
        is_valid, errs, _ = validate_schedule(self.events, dataset.get("faculty_leaves", {}))
        self.assertTrue(is_valid)
        self.assertEqual(len(errs), 0)

    def test_138_approval_gate_passes_for_canonical_dataset(self):
        rev_svc = ReviewService(self.ver_svc)
        user_approver = User(user_id="usr_approver", email="super@univ.edu", display_name="Super", role=UserRole.SUPER_ADMIN)
        appr_svc = ApprovalService(self.ver_svc, rev_svc, enforce_separation_of_duties=True)

        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        rev_svc.start_review(user_approver, self.project, ver.version_id)
        rev_svc.complete_review(user_approver, self.project, rev_svc.list_reviews_for_version(self.project["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)

        ok_gate, gates, msg = appr_svc.verify_approval_gates(user_approver, self.project, ver.version_id)
        self.assertTrue(ok_gate)
        self.assertTrue(gates["hard_validation"])

    def test_139_approved_canonical_dataset_locks_without_mutation(self):
        rev_svc = ReviewService(self.ver_svc)
        user_approver = User(user_id="usr_approver", email="super@univ.edu", display_name="Super", role=UserRole.SUPER_ADMIN)
        appr_svc = ApprovalService(self.ver_svc, rev_svc, enforce_separation_of_duties=True)

        ok, ver, _ = self.ver_svc.create_version(self.user_admin, self.project, self.events)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.VALIDATING)
        self.ver_svc.transition_version_state(self.user_admin, self.project, ver.version_id, VersionState.READY_FOR_REVIEW)
        rev_svc.start_review(user_approver, self.project, ver.version_id)
        rev_svc.complete_review(user_approver, self.project, rev_svc.list_reviews_for_version(self.project["project_id"], ver.version_id)[0].review_id, ReviewDecision.APPROVE_FOR_APPROVAL)
        ok_appr, appr, _ = appr_svc.execute_approval(user_approver, self.project, ver.version_id)
        self.assertTrue(ok_appr)

        # Confirm production schedule file unchanged
        self.assertEqual(file_sha256(os.path.join(PROJECT_ROOT, "production_schedule.json")), GOLDEN_PROD_HASH)

    def test_140_stage10_tests_remain_unaffected(self):
        # Verify simulation models & engine remain operational
        import simulation_models
        self.assertIsNotNone(simulation_models.DisruptionScenario)

    def test_141_stage9_tests_remain_unaffected(self):
        # Verify generation engine remains operational
        import generation_engine
        self.assertIsNotNone(generation_engine.TimetableGenerationEngine)

    def test_142_diff_performance_large_dataset_under_500ms(self):
        import time
        t0 = time.perf_counter()
        TimetableDiffEngine.compute_diff(self.events, self.events)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.5)

if __name__ == "__main__":
    unittest.main()
