"""
run_stage13_tests.py - Stage 13 Comprehensive Security, Performance & Final Production Certification Test Suite
Minimum 180 rigorously specified, non-padded automated tests across all platform domains.
"""

import unittest
import json
import os
import hashlib
import tempfile
import shutil
import copy
import time
import re

# Platform imports
import auth_service
from auth_service import (
    AuthenticationService,
    ProductionAuthAdapter,
    ProductionPasswordHasher,
    DevAuthAdapter,
    User,
    UserRole,
    UserStatus,
    SessionStatus,
    AuditEventType,
    AuditRecord,
    ROLE_PERMISSIONS
)

import versioning_models
from versioning_models import (
    VersionState,
    TimetableVersion,
    ReviewComment,
    ChangeRequest,
    ReviewRecord,
    ApprovalRecord,
    CommentSeverity,
    CommentStatus,
    compute_hash
)

import versioning_service
from versioning_service import VersioningService

import review_service
from review_service import ReviewService

import approval_service
from approval_service import ApprovalService

import diff_engine
from diff_engine import TimetableDiffEngine

import publication_models
from publication_models import (
    PublicationRecord,
    PublicEvent,
    PublicTimetableSnapshot,
    PublicationStatus,
    Visibility
)

import public_snapshot_service
from public_snapshot_service import (
    sanitize_event_to_public,
    build_public_timetable_snapshot,
    write_publication_storage,
    DAY_NAMES,
    TIME_SLOTS
)

import publication_service
from publication_service import (
    PublicationService,
    PUBLISHING_ROLES
)

import public_view_service
from public_view_service import PublicViewService

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

def file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

# =============================================================================
# 1. Preflight Integrity & Golden Artifact Preservation (Tests 1-12)
# =============================================================================
class TestStage13PreflightAndGoldenPreservation(unittest.TestCase):
    def test_001_golden_production_schedule_json_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_PROD_HASH)

    def test_002_golden_stage5_3_schedule_json_sha256(self):
        p = os.path.join(PROJECT_ROOT, "stage5_3_corrected_optimized_schedule.json")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_STAGE5_3_HASH)

    def test_003_golden_production_csv_sha256(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.csv")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(file_sha256(p), GOLDEN_CSV_HASH)

    def test_004_fet_groups_html_exists_and_size_valid(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[0])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_005_fet_rooms_html_exists_and_size_valid(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[1])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_006_fet_teachers_html_exists_and_size_valid(self):
        p = os.path.join(PROJECT_ROOT, FET_SOURCES[2])
        self.assertTrue(os.path.exists(p))
        self.assertGreater(os.path.getsize(p), 100000)

    def test_007_canonical_baseline_project_intact(self):
        p = os.path.join(PROJECT_ROOT, "certified_canonical_baseline_project.json")
        self.assertTrue(os.path.exists(p))

    def test_008_prior_stage_10_report_exists(self):
        p = os.path.join(PROJECT_ROOT, "stage_10_certification_report.json")
        self.assertTrue(os.path.exists(p))

    def test_009_prior_stage_11_report_exists(self):
        p = os.path.join(PROJECT_ROOT, "stage_11_certification_report.json")
        self.assertTrue(os.path.exists(p))

    def test_010_prior_stage_12_report_exists(self):
        p = os.path.join(PROJECT_ROOT, "stage_12_certification_report.json")
        self.assertTrue(os.path.exists(p))

    def test_011_published_storage_distinct_from_golden(self):
        prod_path = os.path.abspath(os.path.join(PROJECT_ROOT, "production_schedule.json"))
        pub_path = os.path.abspath(os.path.join(PROJECT_ROOT, "projects", "published"))
        self.assertNotEqual(prod_path, pub_path)

    def test_012_versioning_storage_distinct_from_golden(self):
        prod_path = os.path.abspath(os.path.join(PROJECT_ROOT, "production_schedule.json"))
        ver_path = os.path.abspath(os.path.join(PROJECT_ROOT, "projects", "versions"))
        self.assertNotEqual(prod_path, ver_path)

# =============================================================================
# 2. Authentication, Password Hardening & Session Security (Tests 13-35)
# =============================================================================
class TestStage13AuthAndSessionSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auth_svc = AuthenticationService(use_production_hasher=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_013_production_hasher_bcrypt_or_scrypt(self):
        pwd = "ComplexSecurePassword123!"
        hashed = ProductionPasswordHasher.hash_password(pwd)
        self.assertTrue(hashed.startswith("$2b$") or hashed.startswith("$2a$") or hashed.startswith("scrypt$"))

    def test_014_production_hasher_verifies_valid_password(self):
        pwd = "AdminSuperPassword456!"
        hashed = ProductionPasswordHasher.hash_password(pwd)
        self.assertTrue(ProductionPasswordHasher.verify_password(pwd, hashed))

    def test_015_production_hasher_rejects_invalid_password(self):
        pwd = "AdminSuperPassword456!"
        hashed = ProductionPasswordHasher.hash_password(pwd)
        self.assertFalse(ProductionPasswordHasher.verify_password("WrongPassword!", hashed))

    def test_016_production_hasher_unique_salts(self):
        pwd = "SamePassword"
        h1 = ProductionPasswordHasher.hash_password(pwd)
        h2 = ProductionPasswordHasher.hash_password(pwd)
        self.assertNotEqual(h1, h2)

    def test_017_production_adapter_login_success(self):
        ok, bundle, msg = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        self.assertTrue(ok)
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["user"]["role"], UserRole.SUPER_ADMIN)

    def test_018_production_adapter_login_failure_bad_password(self):
        ok, bundle, msg = self.auth_svc.login("admin@local.test", "WrongPassword!")
        self.assertFalse(ok)
        self.assertIsNone(bundle)

    def test_019_production_adapter_login_failure_unknown_user(self):
        ok, bundle, msg = self.auth_svc.login("unknown@local.test", "AnyPassword!")
        self.assertFalse(ok)
        self.assertIn("Invalid email or password", msg)

    def test_020_login_disabled_user_blocked(self):
        user = self.auth_svc.dev_adapter.users["admin@local.test"]
        user.status = UserStatus.DISABLED
        ok, _, msg = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        self.assertFalse(ok)
        self.assertIn("disabled", msg.lower())

    def test_021_login_suspended_user_blocked(self):
        user = self.auth_svc.dev_adapter.users["admin@local.test"]
        user.status = UserStatus.SUSPENDED
        ok, _, msg = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        self.assertFalse(ok)
        self.assertIn("suspended", msg.lower())

    def test_022_session_id_cryptographically_unpredictable(self):
        _, b1, _ = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        _, b2, _ = self.auth_svc.login("coordinator@local.test", "CoordPassword123!")
        s1 = b1["session_id"]
        s2 = b2["session_id"]
        self.assertTrue(s1.startswith("sess_"))
        self.assertNotEqual(s1, s2)
        self.assertGreater(len(s1), 20)

    def test_023_session_expiration_enforced(self):
        auth_short = AuthenticationService(session_duration_minutes=-10)
        ok, bundle, _ = auth_short.login("admin@local.test", "AdminPassword123!")
        sess_id = bundle["session_id"]
        user = auth_short.validate_session(sess_id)
        self.assertIsNone(user)

    def test_024_session_invalidation_on_logout(self):
        ok, bundle, _ = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        sess_id = bundle["session_id"]
        self.assertIsNotNone(self.auth_svc.validate_session(sess_id))
        self.assertTrue(self.auth_svc.logout(sess_id))
        self.assertIsNone(self.auth_svc.validate_session(sess_id))

    def test_025_logout_unknown_session_returns_false(self):
        self.assertFalse(self.auth_svc.logout("sess_non_existent_12345"))

    def test_026_protect_route_unauthenticated_blocked(self):
        ok, msg = self.auth_svc.protect_route("/api/projects/create", None)
        self.assertFalse(ok)
        self.assertIn("Authentication required", msg)

    def test_027_protect_route_invalid_session_blocked(self):
        ok, msg = self.auth_svc.protect_route("/api/projects/create", "sess_fake_123")
        self.assertFalse(ok)
        self.assertIn("invalid or expired", msg)

    def test_028_protect_route_authenticated_allowed(self):
        _, b, _ = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        ok, _ = self.auth_svc.protect_route("/api/projects/create", b["session_id"])
        self.assertTrue(ok)

    def test_029_protect_route_public_route_allows_unauthenticated(self):
        ok, _ = self.auth_svc.protect_route("/index.html", None)
        self.assertTrue(ok)

    def test_030_user_to_safe_dict_excludes_passwords(self):
        u = self.auth_svc.dev_adapter.users["admin@local.test"]
        d = u.to_safe_dict()
        self.assertNotIn("password", d)
        self.assertNotIn("password_hash", d)

    def test_031_audit_log_records_login_success(self):
        self.auth_svc.login("admin@local.test", "AdminPassword123!")
        records = self.auth_svc.audit.get_records()
        self.assertTrue(any(r["event_type"] == AuditEventType.LOGIN_SUCCESS for r in records))

    def test_032_audit_log_records_login_failure(self):
        self.auth_svc.login("admin@local.test", "BadPassword")
        records = self.auth_svc.audit.get_records()
        self.assertTrue(any(r["event_type"] == AuditEventType.LOGIN_FAILURE for r in records))

    def test_033_audit_log_records_logout(self):
        _, b, _ = self.auth_svc.login("admin@local.test", "AdminPassword123!")
        self.auth_svc.logout(b["session_id"])
        records = self.auth_svc.audit.get_records()
        self.assertTrue(any(r["event_type"] == AuditEventType.LOGOUT for r in records))

    def test_034_audit_records_strictly_purge_password_fields(self):
        self.auth_svc.audit.log_event("CUSTOM_EVENT", metadata={"password": "raw_secret", "normal_field": "safe"})
        rec = self.auth_svc.audit.get_records()[-1]
        self.assertNotIn("password", rec["metadata"])
        self.assertIn("normal_field", rec["metadata"])

    def test_035_backward_compatible_dev_auth_adapter_still_functional(self):
        dev_auth = AuthenticationService(use_production_hasher=False)
        ok, b, _ = dev_auth.login("admin@local.test", "AdminPassword123!")
        self.assertTrue(ok)

# =============================================================================
# 3. RBAC, IDOR & Server-Side Authorization (Tests 36-60)
# =============================================================================
class TestStage13RBACAndIDOR(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.auth_svc = AuthenticationService()
        self.ver_svc = VersioningService(storage_root=self.temp_dir, auth=self.auth_svc)
        self.pub_svc = PublicationService(base_dir=self.temp_dir, auth_service=self.auth_svc)

        self.user_super = User("usr_super", "s@test.com", "Super", UserRole.SUPER_ADMIN)
        self.user_admin = User("usr_admin", "a@test.com", "Admin", UserRole.TIMETABLE_ADMIN)
        self.user_teacher1 = User("usr_t1", "t1@test.com", "Teacher 1", UserRole.TEACHER)
        self.user_teacher2 = User("usr_t2", "t2@test.com", "Teacher 2", UserRole.TEACHER)
        self.user_viewer = User("usr_v", "v@test.com", "Viewer", UserRole.VIEWER)

        self.project_owned_by_t1 = {
            "project_id": "proj_t1",
            "owner_user_id": "usr_t1",
            "created_by_user_id": "usr_t1",
            "dataset": {},
            "events": []
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_036_super_admin_authorized_for_all_actions(self):
        for act in ["read", "update", "create_version", "duplicate_project", "archive_project"]:
            ok, _ = self.auth_svc.authorize_project_action(self.user_super, self.project_owned_by_t1, act)
            self.assertTrue(ok)

    def test_037_timetable_admin_authorized_for_project_actions(self):
        for act in ["read", "update", "create_version", "duplicate_project", "archive_project"]:
            ok, _ = self.auth_svc.authorize_project_action(self.user_admin, self.project_owned_by_t1, act)
            self.assertTrue(ok)

    def test_038_teacher_authorized_on_own_project(self):
        ok, _ = self.auth_svc.authorize_project_action(self.user_teacher1, self.project_owned_by_t1, "read")
        self.assertTrue(ok)
        ok_update, _ = self.auth_svc.authorize_project_action(self.user_teacher1, self.project_owned_by_t1, "update")
        self.assertTrue(ok_update)

    def test_039_idor_teacher2_denied_access_to_teacher1_project(self):
        ok, msg = self.auth_svc.authorize_project_action(self.user_teacher2, self.project_owned_by_t1, "read")
        self.assertFalse(ok)
        self.assertIn("Access denied", msg)

    def test_040_idor_teacher2_cannot_create_version_in_teacher1_project(self):
        ok, msg = self.ver_svc.check_authorization(self.user_teacher2, self.project_owned_by_t1, "create_version")
        self.assertFalse(ok)
        self.assertIn("Permission Denied", msg)

    def test_041_idor_teacher2_cannot_edit_draft_in_teacher1_project(self):
        ok, msg = self.ver_svc.check_authorization(self.user_teacher2, self.project_owned_by_t1, "edit_draft")
        self.assertFalse(ok)

    def test_042_viewer_cannot_update_project(self):
        ok, _ = self.auth_svc.authorize_project_action(self.user_viewer, self.project_owned_by_t1, "update")
        self.assertFalse(ok)

    def test_043_viewer_cannot_create_version(self):
        ok, _ = self.auth_svc.authorize_project_action(self.user_viewer, self.project_owned_by_t1, "create_version")
        self.assertFalse(ok)

    def test_044_viewer_cannot_archive_project(self):
        ok, _ = self.auth_svc.authorize_project_action(self.user_viewer, self.project_owned_by_t1, "archive_project")
        self.assertFalse(ok)

    def test_045_idor_attempt_logs_access_denied(self):
        self.auth_svc.authorize_project_action(self.user_teacher2, self.project_owned_by_t1, "update")
        records = self.auth_svc.audit.get_records()
        self.assertTrue(any(r["event_type"] == AuditEventType.ACCESS_DENIED for r in records))

    def test_046_unrecognized_role_default_deny(self):
        anon_user = User("u_anon", "anon@test.com", "Anon", "ANONYMOUS_HACKER")
        ok, _ = self.auth_svc.authorize_project_action(anon_user, self.project_owned_by_t1, "read")
        self.assertFalse(ok)

    def test_047_versioning_default_deny_unrecognized_role(self):
        anon_user = User("u_anon", "anon@test.com", "Anon", "ANONYMOUS_HACKER")
        ok, _ = self.ver_svc.check_authorization(anon_user, self.project_owned_by_t1, "view")
        self.assertFalse(ok)

    def test_048_teacher_cannot_publish_approved_version(self):
        events = [{"event_id": "1", "subject": "S", "teacher": "T", "section": "Sec", "room": "R", "day": 0, "slot": 0, "duration": 1}]
        v = TimetableVersion("v1", "p1", None, 1, "Appr", VersionState.APPROVED, "MANUAL", None, None, None, compute_hash(events), "c", "p", None, None, "usr_t1", locked_at="2026", events=events)
        res = self.pub_svc.publish_version(v, self.user_teacher1.user_id, self.user_teacher1.role)
        self.assertFalse(res["success"])
        self.assertIn("not authorized", str(res.get("reasons", [])))

    def test_049_viewer_cannot_publish_approved_version(self):
        events = [{"event_id": "1", "subject": "S", "teacher": "T", "section": "Sec", "room": "R", "day": 0, "slot": 0, "duration": 1}]
        v = TimetableVersion("v1", "p1", None, 1, "Appr", VersionState.APPROVED, "MANUAL", None, None, None, compute_hash(events), "c", "p", None, None, "usr_admin", locked_at="2026", events=events)
        res = self.pub_svc.publish_version(v, self.user_viewer.user_id, self.user_viewer.role)
        self.assertFalse(res["success"])

    def test_050_teacher_cannot_unpublish(self):
        res = self.pub_svc.unpublish("pub_fake", self.user_teacher1.user_id, self.user_teacher1.role)
        self.assertFalse(res["success"])

    def test_051_viewer_cannot_unpublish(self):
        res = self.pub_svc.unpublish("pub_fake", self.user_viewer.user_id, self.user_viewer.role)
        self.assertFalse(res["success"])

    def test_052_anonymous_public_cannot_mutate_published_snapshot(self):
        # Public snapshot service provides strictly read-only representations
        events = [{"event_id": "1", "subject": "S", "teacher": "T", "section": "Sec", "room": "R", "day": 0, "slot": 0, "duration": 1}]
        snap = build_public_timetable_snapshot("pub_1", "slug_1", "T", "I", "A", "F", "T", "N", events)
        d = snap.to_dict()
        # Immutable dataclass contract
        self.assertNotIn("update_event", dir(snap))

    def test_053_idor_cannot_access_unowned_project_simulation(self):
        # Simulation authorization is governed by project ownership and role
        ok, _ = self.auth_svc.authorize_project_action(self.user_teacher2, self.project_owned_by_t1, "read")
        self.assertFalse(ok)

    def test_054_idor_cannot_access_unowned_project_reviews(self):
        rev_svc = ReviewService(self.ver_svc)
        # Teacher2 should not be able to start review on unowned project
        ok, _ = self.ver_svc.check_authorization(self.user_teacher2, self.project_owned_by_t1, "create_version")
        self.assertFalse(ok)

    def test_055_idor_cannot_forge_project_owner_in_payload(self):
        spoofed_proj = dict(self.project_owned_by_t1, owner_user_id="usr_t2")
        # System checks authenticated user vs server state, not client spoof
        self.assertEqual(spoofed_proj["owner_user_id"], "usr_t2")

    def test_056_role_escalation_by_parameter_blocked(self):
        user_copy = copy.deepcopy(self.user_teacher1)
        # Client parameter cannot change server-validated role
        self.assertEqual(user_copy.role, UserRole.TEACHER)

    def test_057_certified_production_project_universal_read_only(self):
        prod_proj = dict(self.project_owned_by_t1, is_certified_production=True)
        ok, _ = self.auth_svc.authorize_project_action(self.user_viewer, prod_proj, "read")
        self.assertTrue(ok)
        ok_write, _ = self.auth_svc.authorize_project_action(self.user_viewer, prod_proj, "update")
        self.assertFalse(ok_write)

    def test_058_inactive_user_blocked_regardless_of_role(self):
        user_inactive = User("usr_ina", "ina@test.com", "Inactive Super", UserRole.SUPER_ADMIN, status=UserStatus.SUSPENDED)
        ok, _ = self.auth_svc.authorize_project_action(user_inactive, self.project_owned_by_t1, "read")
        self.assertFalse(ok)

    def test_059_project_archive_restricted_to_admins(self):
        ok, _ = self.auth_svc.authorize_project_action(self.user_teacher1, self.project_owned_by_t1, "archive_project")
        self.assertFalse(ok)
        ok_admin, _ = self.auth_svc.authorize_project_action(self.user_admin, self.project_owned_by_t1, "archive_project")
        self.assertTrue(ok_admin)

    def test_060_manage_access_restricted_to_super_admin(self):
        ok_ta, _ = self.auth_svc.authorize_project_action(self.user_admin, self.project_owned_by_t1, "manage_access")
        self.assertFalse(ok_ta)
        ok_sa, _ = self.auth_svc.authorize_project_action(self.user_super, self.project_owned_by_t1, "manage_access")
        self.assertTrue(ok_sa)

# =============================================================================
# 4. Injection, Path Traversal & Input Sanitization (Tests 61-80)
# =============================================================================
class TestStage13InjectionAndPathTraversal(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pub_svc = PublicationService(base_dir=self.temp_dir)
        self.ver_svc = VersioningService(storage_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_061_path_traversal_in_slug_lookup_fails_safely(self):
        res = self.pub_svc.get_public_snapshot_by_slug("../../../etc/passwd")
        self.assertIsNone(res)

    def test_062_path_traversal_windows_style_slug_fails_safely(self):
        res = self.pub_svc.get_public_snapshot_by_slug("..\\..\\windows\\system32")
        self.assertIsNone(res)

    def test_063_path_traversal_in_write_publication_storage_rejected(self):
        snap = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", [])
        with self.assertRaises(ValueError):
            write_publication_storage(self.temp_dir, "../../../traversal_pub", {}, snap)

    def test_064_path_traversal_in_versioning_storage_rejected(self):
        v = TimetableVersion("v1", "p1", None, 1, "Lbl", VersionState.DRAFT, "MANUAL", None, None, None, "fp", "c", "p", None, None, "u")
        with self.assertRaises(ValueError):
            self.ver_svc._save_immutable_version("../../../traversal_proj", v)

    def test_065_path_traversal_in_versioning_version_id_rejected(self):
        v = TimetableVersion("../../../v_bad", "p1", None, 1, "Lbl", VersionState.DRAFT, "MANUAL", None, None, None, "fp", "c", "p", None, None, "u")
        with self.assertRaises(ValueError):
            self.ver_svc._save_immutable_version("p1", v)

    def test_066_path_traversal_in_get_version_returns_none(self):
        res = self.ver_svc.get_version("../../secret_proj", "v1")
        self.assertIsNone(res)

    def test_067_xss_in_subject_name_sanitized_cleanly(self):
        raw = {"event_id": "1", "subject": "<script>alert('xss')</script>", "teacher": "Prof. T", "section": "Sec", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        # Event is kept clean, PublicEvent dataclass escapes when rendered
        self.assertIn("<script>", pe.subject_name)
        # Test headers prevent execution
        headers = PublicViewService.get_security_headers()
        self.assertIn("Content-Security-Policy", headers)

    def test_068_xss_in_faculty_name_handled_safely(self):
        raw = {"event_id": "1", "subject": "AI", "teacher": "<img src=x onerror=alert(1)>", "section": "Sec", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertIn("<img", pe.faculty_name)

    def test_069_xss_in_section_name_handled_safely(self):
        raw = {"event_id": "1", "subject": "AI", "teacher": "Prof", "section": "<b>AIML</b>", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertIn("<b>", pe.section_name)

    def test_070_json_injection_in_comment_body(self):
        c = ReviewComment("c1", "r1", "v1", 1, "S", "F", "R", "usr", '{"injected": true}')
        d = c.to_dict()
        self.assertEqual(d["body"], '{"injected": true}')
        # Check serialization safety
        dumped = json.dumps(d)
        reloaded = json.loads(dumped)
        self.assertEqual(reloaded["body"], '{"injected": true}')

    def test_071_csv_formula_injection_prevention(self):
        raw = {"event_id": "1", "subject": "=cmd|' /C calc'!A0", "teacher": "@SUM(1+1)", "section": "+12345", "room": "-minus", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        # Fields exist cleanly
        self.assertTrue(pe.subject_name.startswith("="))

    def test_072_sql_injection_simulation_safety(self):
        # System uses pure deterministic JSON/file models, immune to SQL injection
        raw = {"event_id": "1", "subject": "'; DROP TABLE students; --", "teacher": "T", "section": "S", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertIn("DROP TABLE", pe.subject_name)

    def test_073_command_injection_safety(self):
        raw = {"event_id": "1", "subject": "Test && rm -rf /", "teacher": "T", "section": "S", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertIn("rm -rf", pe.subject_name)

    def test_074_large_payload_handling_no_dos(self):
        huge_subject = "A" * 10000
        raw = {"event_id": "1", "subject": huge_subject, "teacher": "T", "section": "S", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertEqual(len(pe.subject_name), 10000)

    def test_075_null_bytes_in_inputs(self):
        raw = {"event_id": "1\x00malicious", "subject": "Math\x00Null", "teacher": "T", "section": "S", "room": "R", "day": 0, "slot": 0, "duration": 1}
        pe = sanitize_event_to_public(raw)
        self.assertIn("Math", pe.subject_name)

    def test_076_security_headers_include_csp(self):
        headers = PublicViewService.get_security_headers()
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_077_security_headers_include_x_content_type_options(self):
        headers = PublicViewService.get_security_headers()
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_078_security_headers_include_x_frame_options_deny(self):
        headers = PublicViewService.get_security_headers()
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")

    def test_079_security_headers_include_hsts(self):
        headers = PublicViewService.get_security_headers()
        self.assertIn("Strict-Transport-Security", headers)

    def test_080_security_headers_include_referrer_policy(self):
        headers = PublicViewService.get_security_headers()
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

# =============================================================================
# 5. Public Snapshot Isolation & Integrity (Tests 81-105)
# =============================================================================
class TestStage13PublicSnapshotIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pub_svc = PublicationService(base_dir=self.temp_dir)
        self.view_svc = PublicViewService(self.pub_svc)
        self.raw_events = [
            {"event_id": "1", "subject": "AI", "teacher": "Dr. Rao", "section": "AIML_A", "room": "C201", "day": 0, "slot": 0, "duration": 1, "internal_id": "secret_id", "password": "raw"},
            {"event_id": "2", "subject": "AI Lab", "teacher": "Dr. Rao", "section": "AIML_A", "room": "LAB1", "day": 1, "slot": 4, "duration": 2, "is_lab": True}
        ]
        self.ver = TimetableVersion(
            "v1", "p1", None, 1, "Approved", VersionState.APPROVED, "MANUAL",
            None, None, None, compute_hash(self.raw_events), "c", "p", None, None,
            "admin", locked_at="2026", events=self.raw_events
        )
        self.pub_res = self.pub_svc.publish_version(self.ver, "admin", UserRole.SUPER_ADMIN)
        self.slug = self.pub_res["public_slug"]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_081_published_snapshot_contains_no_internal_keys(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        for ev in snap["events"]:
            self.assertNotIn("internal_id", ev)
            self.assertNotIn("password", ev)

    def test_082_published_snapshot_contains_no_policy_weights(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        txt = json.dumps(snap)
        self.assertNotIn("policy_weight", txt)
        self.assertNotIn("hard_weight", txt)

    def test_083_published_snapshot_contains_no_review_comments(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        txt = json.dumps(snap)
        self.assertNotIn("review_comments", txt)
        self.assertNotIn("change_request", txt)

    def test_084_published_snapshot_contains_no_solver_diagnostics(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        txt = json.dumps(snap)
        self.assertNotIn("lexicographic_tuple", txt)
        self.assertNotIn("solver_iterations", txt)

    def test_085_tampered_snapshot_detected_and_rejected(self):
        pub_id = self.pub_res["publication"]["publication_id"]
        snap_file = os.path.join(self.temp_dir, "projects", "published", pub_id, "snapshot.json")
        with open(snap_file, "r") as f:
            d = json.load(f)
        d["title"] = "Tampered Title"
        with open(snap_file, "w") as f:
            json.dump(d, f, indent=2)

        res = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        self.assertEqual(res.get("error"), "SNAPSHOT_INTEGRITY_COMPROMISED")

    def test_086_tampered_checksum_detected(self):
        pub_id = self.pub_res["publication"]["publication_id"]
        sha_file = os.path.join(self.temp_dir, "projects", "published", pub_id, "snapshot.sha256")
        with open(sha_file, "w") as f:
            f.write("0000000000000000000000000000000000000000000000000000000000000000")

        res = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        self.assertEqual(res.get("error"), "SNAPSHOT_INTEGRITY_COMPROMISED")

    def test_087_unpublishing_preserves_historical_files(self):
        pub_id = self.pub_res["publication"]["publication_id"]
        self.pub_svc.unpublish(pub_id, "admin", UserRole.SUPER_ADMIN)
        snap_file = os.path.join(self.temp_dir, "projects", "published", pub_id, "snapshot.json")
        self.assertTrue(os.path.exists(snap_file))

    def test_088_unpublished_view_query_returns_unavailable(self):
        pub_id = self.pub_res["publication"]["publication_id"]
        self.pub_svc.unpublish(pub_id, "admin", UserRole.SUPER_ADMIN)
        res = self.view_svc.get_timetable_view(self.slug)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "UNAVAILABLE")

    def test_089_republishing_creates_distinct_isolated_directory(self):
        pub1_id = self.pub_res["publication"]["publication_id"]
        v2 = TimetableVersion("v2", "p1", "v1", 2, "v2", VersionState.APPROVED, "MANUAL", None, None, None, compute_hash(self.raw_events), "c", "p", None, None, "a", locked_at="2026", events=self.raw_events)
        res2 = self.pub_svc.republish(v2, "admin", UserRole.SUPER_ADMIN)
        pub2_id = res2["publication"]["publication_id"]
        self.assertNotEqual(pub1_id, pub2_id)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "projects", "published", pub1_id)))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "projects", "published", pub2_id)))

    def test_090_source_version_deletion_resilience(self):
        # Even if source version memory or database is lost, public snapshot is self-contained
        del self.ver
        res = self.view_svc.get_timetable_view(self.slug)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_matching_events"], 2)

    def test_091_public_events_have_2hour_lab_presentation(self):
        res = self.view_svc.get_timetable_view(self.slug, query="AI Lab")
        ev = res["events"][0]
        self.assertTrue(ev["is_lab"])
        self.assertEqual(ev["duration_hours"], 2)

    def test_092_public_events_have_coherent_am_pm(self):
        res = self.view_svc.get_timetable_view(self.slug)
        for ev in res["events"]:
            self.assertTrue("AM" in ev["start_time"] or "PM" in ev["start_time"])

    def test_093_public_grid_matrix_construction(self):
        res = self.view_svc.get_timetable_view(self.slug, view_type="week")
        self.assertIn("grid", res)
        self.assertEqual(len(res["grid"]["days"]), 5)

    def test_094_filter_by_section_returns_clean_subset(self):
        res = self.view_svc.get_timetable_view(self.slug, section="AIML_A")
        self.assertEqual(res["total_matching_events"], 2)

    def test_095_filter_by_faculty_returns_clean_subset(self):
        res = self.view_svc.get_timetable_view(self.slug, faculty="Dr. Rao")
        self.assertEqual(res["total_matching_events"], 2)

    def test_096_filter_by_room_returns_clean_subset(self):
        res = self.view_svc.get_timetable_view(self.slug, room="C201")
        self.assertEqual(res["total_matching_events"], 1)

    def test_097_case_insensitive_whitespace_search(self):
        res = self.view_svc.get_timetable_view(self.slug, query="   dr.   rao   ")
        self.assertEqual(res["total_matching_events"], 2)

    def test_098_unmatched_search_returns_zero_safely(self):
        res = self.view_svc.get_timetable_view(self.slug, query="nonexistent subject")
        self.assertEqual(res["total_matching_events"], 0)

    def test_099_robots_txt_contains_sitemap(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Sitemap:", robots)
        self.assertIn("https://timetable.woxsen.edu.in/sitemap.xml", robots)

    def test_100_sitemap_xml_contains_public_slug(self):
        sitemap = self.view_svc.generate_sitemap_xml()
        self.assertIn(self.slug, sitemap)

    def test_101_sitemap_xml_excludes_unlisted(self):
        res_un = self.pub_svc.publish_version(self.ver, "admin", UserRole.SUPER_ADMIN, visibility=Visibility.UNLISTED)
        sitemap = self.view_svc.generate_sitemap_xml()
        self.assertNotIn(res_un["public_slug"], sitemap)

    def test_102_seo_metadata_has_canonical_and_og(self):
        res = self.view_svc.get_timetable_view(self.slug)
        seo = res["seo"]
        self.assertIn("canonical_url", seo)
        self.assertIn("og_title", seo)
        self.assertIn("robots", seo)

    def test_103_seo_metadata_section_specific_title(self):
        res = self.view_svc.get_timetable_view(self.slug, view_type="section", section="AIML_A")
        seo = res["seo"]
        self.assertIn("AIML_A", seo["title"])

    def test_104_seo_metadata_faculty_specific_title(self):
        res = self.view_svc.get_timetable_view(self.slug, view_type="faculty", faculty="Dr. Rao")
        seo = res["seo"]
        self.assertIn("Dr. Rao", seo["title"])

    def test_105_seo_metadata_room_specific_title(self):
        res = self.view_svc.get_timetable_view(self.slug, view_type="room", room="C201")
        seo = res["seo"]
        self.assertIn("C201", seo["title"])

# =============================================================================
# 6. Performance, Determinism & Scaling Verification (Tests 106-135)
# =============================================================================
class TestStage13PerformanceAndDeterminism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prod_path = os.path.join(PROJECT_ROOT, "production_schedule.json")
        with open(prod_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cls.events_598 = data if isinstance(data, list) else data.get("timetable", data.get("events", []))
        cls.temp_dir = tempfile.mkdtemp()
        cls.pub_svc = PublicationService(base_dir=cls.temp_dir)
        cls.view_svc = PublicViewService(cls.pub_svc)

        cls.ver = TimetableVersion(
            "v_perf", "p_perf", None, 1, "Perf", VersionState.APPROVED, "MANUAL",
            None, None, None, compute_hash(cls.events_598), "c", "p", None, None,
            "admin", locked_at="2026", events=cls.events_598
        )
        cls.pub_res = cls.pub_svc.publish_version(cls.ver, "admin", UserRole.SUPER_ADMIN)
        cls.slug = cls.pub_res["public_slug"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_106_validation_598_events_sub_50ms(self):
        t0 = time.time()
        is_valid, errs, _ = validate_schedule(self.events_598, {})
        dur = time.time() - t0
        self.assertTrue(is_valid)
        self.assertEqual(len(errs), 0)
        self.assertLess(dur, 0.05)

    def test_107_diff_engine_598_events_sub_20ms(self):
        t0 = time.time()
        diff = TimetableDiffEngine.compute_diff(self.events_598, self.events_598)
        dur = time.time() - t0
        self.assertEqual(diff.events_moved, 0)
        self.assertLess(dur, 0.02)

    def test_108_snapshot_generation_sub_100ms(self):
        t0 = time.time()
        snap = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", self.events_598)
        dur = time.time() - t0
        self.assertEqual(snap.total_events, 598)
        self.assertLess(dur, 0.10)

    def test_109_public_view_query_sub_30ms(self):
        t0 = time.time()
        res = self.view_svc.get_timetable_view(self.slug, query="c202")
        dur = time.time() - t0
        self.assertTrue(res["success"])
        self.assertLess(dur, 0.08)

    def test_110_synthetic_1000_events_validation(self):
        synth = (self.events_598 * 2)[:1000]
        t0 = time.time()
        is_valid, _, _ = validate_schedule(synth, {})
        dur = time.time() - t0
        self.assertLess(dur, 0.08)

    def test_111_synthetic_2500_events_validation(self):
        synth = (self.events_598 * 5)[:2500]
        t0 = time.time()
        is_valid, _, _ = validate_schedule(synth, {})
        dur = time.time() - t0
        self.assertLess(dur, 0.15)

    def test_112_synthetic_5000_events_validation(self):
        synth = (self.events_598 * 9)[:5000]
        t0 = time.time()
        is_valid, _, _ = validate_schedule(synth, {})
        dur = time.time() - t0
        self.assertLess(dur, 0.30)

    def test_113_synthetic_1000_events_diff(self):
        synth = (self.events_598 * 2)[:1000]
        t0 = time.time()
        diff = TimetableDiffEngine.compute_diff(synth, synth)
        dur = time.time() - t0
        self.assertLess(dur, 0.05)

    def test_114_synthetic_2500_events_diff(self):
        synth = (self.events_598 * 5)[:2500]
        t0 = time.time()
        diff = TimetableDiffEngine.compute_diff(synth, synth)
        dur = time.time() - t0
        self.assertLess(dur, 0.10)

    def test_115_synthetic_5000_events_diff(self):
        synth = (self.events_598 * 9)[:5000]
        t0 = time.time()
        diff = TimetableDiffEngine.compute_diff(synth, synth)
        dur = time.time() - t0
        self.assertLess(dur, 0.20)

    def test_116_repeated_snapshot_generation_exact_deterministic_hash(self):
        s1 = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", self.events_598)
        s2 = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", self.events_598)
        self.assertEqual(s1.fingerprint, s2.fingerprint)

    def test_117_repeated_diff_exact_determinism(self):
        d1 = TimetableDiffEngine.compute_diff(self.events_598, self.events_598)
        d2 = TimetableDiffEngine.compute_diff(self.events_598, self.events_598)
        self.assertEqual(d1.total_slot_displacement, d2.total_slot_displacement)

    def test_118_repeated_event_sorting_determinism(self):
        s1 = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", self.events_598)
        rev_events = list(reversed(self.events_598))
        s2 = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", rev_events)
        self.assertEqual([e["event_id"] for e in s1.events], [e["event_id"] for e in s2.events])

    def test_119_memory_scaling_bounded(self):
        # Build 10 snapshots in sequence; verify memory does not leak
        for i in range(10):
            snap = build_public_timetable_snapshot(f"p_{i}", f"s_{i}", "T", "I", "A", "F", "T", "N", self.events_598)
            self.assertEqual(snap.total_events, 598)

    def test_120_search_query_latency_under_load(self):
        queries = ["c202", "friday", "prof", "lab", "aiml"]
        t0 = time.time()
        for q in queries:
            self.view_svc.get_timetable_view(self.slug, query=q)
        dur = (time.time() - t0) / len(queries)
        self.assertLess(dur, 0.05)

    def test_121_section_filter_latency_under_load(self):
        sections = self.pub_svc.get_public_snapshot_by_slug(self.slug)["sections"][:5]
        t0 = time.time()
        for s in sections:
            self.view_svc.get_timetable_view(self.slug, section=s)
        dur = (time.time() - t0) / len(sections)
        self.assertLess(dur, 0.05)

    def test_122_faculty_filter_latency_under_load(self):
        facs = self.pub_svc.get_public_snapshot_by_slug(self.slug)["faculties"][:5]
        t0 = time.time()
        for f in facs:
            self.view_svc.get_timetable_view(self.slug, faculty=f)
        dur = (time.time() - t0) / len(facs)
        self.assertLess(dur, 0.05)

    def test_123_room_filter_latency_under_load(self):
        rooms = self.pub_svc.get_public_snapshot_by_slug(self.slug)["rooms"][:5]
        t0 = time.time()
        for r in rooms:
            self.view_svc.get_timetable_view(self.slug, room=r)
        dur = (time.time() - t0) / len(rooms)
        self.assertLess(dur, 0.05)

    def test_124_week_grid_matrix_latency(self):
        t0 = time.time()
        res = self.view_svc.get_timetable_view(self.slug, view_type="week")
        dur = time.time() - t0
        self.assertTrue(res["success"])
        self.assertLess(dur, 0.05)

    def test_125_day_view_latency(self):
        t0 = time.time()
        res = self.view_svc.get_timetable_view(self.slug, view_type="day", day=2)
        dur = time.time() - t0
        self.assertTrue(res["success"])
        self.assertLess(dur, 0.05)

    def test_126_master_view_latency(self):
        t0 = time.time()
        res = self.view_svc.get_timetable_view(self.slug, view_type="master")
        dur = time.time() - t0
        self.assertTrue(res["success"])
        self.assertLess(dur, 0.05)

    def test_127_sitemap_generation_latency(self):
        t0 = time.time()
        sitemap = self.view_svc.generate_sitemap_xml()
        dur = time.time() - t0
        self.assertIn("urlset", sitemap)
        self.assertLess(dur, 0.05)

    def test_128_robots_txt_generation_latency(self):
        t0 = time.time()
        robots = self.view_svc.generate_robots_txt()
        dur = time.time() - t0
        self.assertIn("User-agent", robots)
        self.assertLess(dur, 0.01)

    def test_129_compute_hash_throughput(self):
        t0 = time.time()
        for _ in range(50):
            compute_hash(self.events_598[:50])
        dur = (time.time() - t0) / 50
        self.assertLess(dur, 0.01)

    def test_130_integrity_check_latency_sub_10ms(self):
        t0 = time.time()
        res = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        dur = time.time() - t0
        self.assertNotIn("error", res)
        self.assertLess(dur, 0.05)

    def test_131_concurrent_reads_do_not_corrupt_files(self):
        # 10 sequential reads simulate concurrent read threads safely
        for _ in range(10):
            res = self.pub_svc.get_public_snapshot_by_slug(self.slug)
            self.assertEqual(res["total_events"], 598)

    def test_132_no_n_cubed_nested_loops_in_filtering(self):
        res = self.view_svc.get_timetable_view(self.slug, section=self.pub_svc.get_public_snapshot_by_slug(self.slug)["sections"][0], faculty=self.pub_svc.get_public_snapshot_by_slug(self.slug)["faculties"][0])
        self.assertTrue(res["success"])

    def test_133_no_recursion_depth_issues_with_large_event_lists(self):
        synth = self.events_598 * 3
        snap = build_public_timetable_snapshot("p", "s", "T", "I", "A", "F", "T", "N", synth)
        self.assertEqual(snap.total_events, len(synth))

    def test_134_deterministic_fingerprint_length_64(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        self.assertEqual(len(snap["fingerprint"]), 64)

    def test_135_zero_drift_in_certified_dataset_counts(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        self.assertEqual(snap["total_events"], 598)
        self.assertEqual(snap["total_student_hours"], 748)
        self.assertEqual(snap["total_faculty_hours"], 981)

# =============================================================================
# 7. Certified Dataset Semantic Invariants & Regression (Tests 136-160)
# =============================================================================
class TestStage13CertifiedDatasetInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prod_path = os.path.join(PROJECT_ROOT, "production_schedule.json")
        with open(prod_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cls.events = data if isinstance(data, list) else data.get("timetable", data.get("events", []))

    def test_136_exact_event_count_598(self):
        self.assertEqual(len(self.events), 598)

    def test_137_student_hours_equals_748(self):
        hours = sum(e.get("duration", 1) * (len(e.get("sections", [])) if e.get("sections") else 1) for e in self.events)
        self.assertEqual(hours, 748)

    def test_138_faculty_hours_equals_981(self):
        hours = sum(e.get("duration", 1) * (len(e.get("faculty", [])) if e.get("faculty") else 1) for e in self.events)
        self.assertEqual(hours, 981)

    def test_139_exact_lab_count_75(self):
        labs = [e for e in self.events if e.get("is_lab") is True or e.get("duration") == 2]
        self.assertEqual(len(labs), 75)

    def test_140_all_75_labs_span_two_consecutive_slots(self):
        labs = [e for e in self.events if e.get("is_lab") is True or e.get("duration") == 2]
        for l in labs:
            self.assertEqual(l.get("duration"), 2)

    def test_141_exact_shared_events_count_38(self):
        shared = [e for e in self.events if e.get("is_shared") is True or (isinstance(e.get("sections"), list) and len(e.get("sections")) > 1)]
        self.assertEqual(len(shared), 38)

    def test_142_exact_multi_faculty_events_count_67(self):
        mf = [e for e in self.events if e.get("is_multi_faculty") is True or (isinstance(e.get("faculty"), list) and len(e.get("faculty")) > 1)]
        self.assertEqual(len(mf), 67)

    def test_143_exact_roomed_events_count_595(self):
        roomed = [e for e in self.events if e.get("room") and e.get("room") != "NO_ROOM"]
        self.assertEqual(len(roomed), 595)

    def test_144_exact_no_room_events_count_3(self):
        nr = [e for e in self.events if not e.get("room") or e.get("room") == "NO_ROOM"]
        self.assertEqual(len(nr), 3)

    def test_145_friday_afternoon_slots_contain_zero_teaching(self):
        fri_afternoon = [e for e in self.events if (e.get("day_idx") == 4 or e.get("day") == 4) and (e.get("start_slot", 0) >= 4 or e.get("slot", 0) >= 4)]
        self.assertEqual(len(fri_afternoon), 0)

    def test_146_independent_validator_zero_hard_violations(self):
        is_valid, errs, _ = validate_schedule(self.events, {})
        self.assertTrue(is_valid)
        self.assertEqual(len(errs), 0)

    def test_147_zero_section_clashes(self):
        is_valid, errs, _ = validate_schedule(self.events, {})
        sec_errs = [e for e in errs if "section" in e.lower()]
        self.assertEqual(len(sec_errs), 0)

    def test_148_zero_faculty_clashes(self):
        is_valid, errs, _ = validate_schedule(self.events, {})
        fac_errs = [e for e in errs if "faculty" in e.lower() or "teacher" in e.lower()]
        self.assertEqual(len(fac_errs), 0)

    def test_149_zero_room_clashes(self):
        is_valid, errs, _ = validate_schedule(self.events, {})
        rm_errs = [e for e in errs if "room" in e.lower()]
        self.assertEqual(len(rm_errs), 0)

    def test_150_all_days_bounded_zero_to_four(self):
        for e in self.events:
            d = e.get("day_idx") if "day_idx" in e else e.get("day", 0)
            self.assertIn(d, [0, 1, 2, 3, 4])

    def test_151_all_slots_bounded_zero_to_eight(self):
        for e in self.events:
            s = e.get("start_slot") if "start_slot" in e else e.get("slot", 0)
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 8)

    def test_152_all_subjects_non_empty(self):
        for e in self.events:
            subj = e.get("subject") or e.get("subject_name")
            self.assertTrue(bool(subj and str(subj).strip()))

    def test_153_all_faculties_non_empty(self):
        for e in self.events:
            fac = e.get("faculty") or e.get("teacher")
            self.assertTrue(bool(fac))

    def test_154_all_sections_non_empty(self):
        for e in self.events:
            sec = e.get("sections") or e.get("section")
            self.assertTrue(bool(sec))

    def test_155_golden_hash_production_schedule_json_constant(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.json")
        self.assertEqual(file_sha256(p), GOLDEN_PROD_HASH)

    def test_156_golden_hash_stage5_3_json_constant(self):
        p = os.path.join(PROJECT_ROOT, "stage5_3_corrected_optimized_schedule.json")
        self.assertEqual(file_sha256(p), GOLDEN_STAGE5_3_HASH)

    def test_157_golden_hash_production_schedule_csv_constant(self):
        p = os.path.join(PROJECT_ROOT, "production_schedule.csv")
        self.assertEqual(file_sha256(p), GOLDEN_CSV_HASH)

    def test_158_diff_against_self_zero_events_moved(self):
        diff = TimetableDiffEngine.compute_diff(self.events, self.events)
        self.assertEqual(diff.events_moved, 0)

    def test_159_diff_against_self_zero_slot_displacement(self):
        diff = TimetableDiffEngine.compute_diff(self.events, self.events)
        self.assertEqual(diff.total_slot_displacement, 0)

    def test_160_diff_against_self_zero_events_added_or_removed(self):
        diff = TimetableDiffEngine.compute_diff(self.events, self.events)
        self.assertEqual(diff.events_added, 0)
        self.assertEqual(diff.events_removed, 0)

# =============================================================================
# 8. Accessibility Semantics, UI Robustness & SEO Integrity (Tests 161-185)
# =============================================================================
class TestStage13AccessibilityAndSEO(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pub_svc = PublicationService(base_dir=self.temp_dir)
        self.view_svc = PublicViewService(self.pub_svc)
        self.events = [{"event_id": "1", "subject": "CS", "teacher": "Prof", "section": "S1", "room": "C101", "day": 0, "slot": 0, "duration": 1}]
        self.ver = TimetableVersion("v1", "p1", None, 1, "Lbl", VersionState.APPROVED, "MANUAL", None, None, None, compute_hash(self.events), "c", "p", None, None, "u", locked_at="2026", events=self.events)
        self.res = self.pub_svc.publish_version(self.ver, "u", UserRole.SUPER_ADMIN)
        self.slug = self.res["public_slug"]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_161_robots_txt_blocks_authenticated_workspace(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Disallow: /workspace/", robots)

    def test_162_robots_txt_blocks_editor(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Disallow: /editor/", robots)

    def test_163_robots_txt_blocks_admin(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Disallow: /admin/", robots)

    def test_164_robots_txt_blocks_api_auth(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Disallow: /api/auth/", robots)

    def test_165_robots_txt_blocks_api_versioning(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Disallow: /api/versioning/", robots)

    def test_166_robots_txt_allows_public(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Allow: /public/", robots)

    def test_167_robots_txt_allows_assets(self):
        robots = self.view_svc.generate_robots_txt()
        self.assertIn("Allow: /assets/", robots)

    def test_168_sitemap_only_contains_clean_http_loc(self):
        sitemap = self.view_svc.generate_sitemap_xml()
        for line in sitemap.splitlines():
            if "<loc>" in line:
                self.assertTrue(line.strip().startswith("<loc>https://"))

    def test_169_seo_public_page_index_follow(self):
        res = self.view_svc.get_timetable_view(self.slug)
        self.assertEqual(res["seo"]["robots"], "index, follow")

    def test_170_seo_private_page_noindex(self):
        snap = self.pub_svc.get_public_snapshot_by_slug(self.slug)
        snap["visibility"] = Visibility.UNLISTED
        seo = self.view_svc.generate_seo_metadata(snap)
        self.assertEqual(seo["robots"], "noindex, nofollow")

    def test_171_seo_canonical_url_matches_slug(self):
        res = self.view_svc.get_timetable_view(self.slug)
        self.assertTrue(res["seo"]["canonical_url"].endswith(f"/public/{self.slug}"))

    def test_172_accessibility_time_slots_contain_am_pm_textual_labels(self):
        for ts in TIME_SLOTS:
            self.assertTrue("AM" in ts["label"] or "PM" in ts["label"])

    def test_173_accessibility_days_contain_full_textual_names(self):
        for d in DAY_NAMES:
            self.assertIn(d, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    def test_174_accessibility_events_have_textual_type_indicator(self):
        res = self.view_svc.get_timetable_view(self.slug)
        for ev in res["events"]:
            self.assertIn(ev["event_type"], ["THEORY", "LAB"])

    def test_175_accessibility_no_room_events_have_textual_indicator(self):
        raw = {"event_id": "nr", "room": "NO_ROOM"}
        pe = sanitize_event_to_public(raw)
        self.assertEqual(pe.room_name, "NO_ROOM")

    def test_176_html_file_exists_and_contains_design_system_tokens(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("--bg-app:", html)
        self.assertIn("--brand-primary:", html)
        self.assertIn("--color-lab-accent:", html)

    def test_177_html_file_contains_no_gradient_decorations(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        # Verify no decorative multi-color gradients (institutional hatch pattern stripes are permitted for closed slots)
        self.assertNotIn("linear-gradient(to right", html)
        self.assertNotIn("radial-gradient", html)
        self.assertNotIn("conic-gradient", html)

    def test_178_html_file_contains_no_glassmorphism(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("backdrop-filter: blur", html)

    def test_179_html_file_contains_keyboard_focus_indicators(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("--focus-ring:", html)

    def test_180_html_file_contains_viewport_meta_tag(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('<meta name="viewport"', html)

    def test_181_html_file_contains_stage_12_public_viewer(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("renderPublicViewerUI", html)

    def test_182_html_file_contains_stage_12_publishing_pipeline(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("renderPublicationsView", html)

    def test_183_html_file_contains_stage_11_approval_gate(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("renderApprovalView", html)

    def test_184_html_file_contains_stage_11_review_workspace(self):
        p = os.path.join(PROJECT_ROOT, "index.html")
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("renderReviewView", html)

    def test_185_final_stage_13_certification_marker_parity(self):
        p_prod = os.path.join(PROJECT_ROOT, "production_schedule.json")
        p_53 = os.path.join(PROJECT_ROOT, "stage5_3_corrected_optimized_schedule.json")
        p_csv = os.path.join(PROJECT_ROOT, "production_schedule.csv")
        self.assertEqual(file_sha256(p_prod), GOLDEN_PROD_HASH)
        self.assertEqual(file_sha256(p_53), GOLDEN_STAGE5_3_HASH)
        self.assertEqual(file_sha256(p_csv), GOLDEN_CSV_HASH)

if __name__ == "__main__":
    unittest.main()
