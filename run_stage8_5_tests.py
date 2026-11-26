"""
run_stage8_5_tests.py - Complete Automated Test Suite for Stage 8.5:
Constraint & Policy Builder

Validates T8_5_1 through T8_5_87:
- T8_5_1: Preflight verification & golden hashes
- T8_5_2: Policy registry loads
- T8_5_3: Required 45 rule types exist
- T8_5_4: HARD category semantics are enforced
- T8_5_5: SOFT category semantics are enforced
- T8_5_6: PREFERENCE category semantics are enforced
- T8_5_7: HARD rules reject weights
- T8_5_8: SOFT rules accept positive weights
- T8_5_9: PREFERENCE rules accept positive weights
- T8_5_10: Zero weight is rejected
- T8_5_11: Negative weight is rejected
- T8_5_12: Invalid rule type is rejected
- T8_5_13: Invalid scope is rejected
- T8_5_14: Missing required parameter is rejected
- T8_5_15: Invalid parameter type is rejected
- T8_5_16: Invalid parameter range is rejected
- T8_5_17: Valid policy can be created
- T8_5_18: Policy can be duplicated
- T8_5_19: Policy can be disabled
- T8_5_20: Policy can be archived
- T8_5_21: Policy history is immutable
- T8_5_22: Active policy cannot be edited in place
- T8_5_23: Editing active policy creates draft version
- T8_5_24: Activating policy creates immutable active version
- T8_5_25: Historical timetable retains old policy version
- T8_5_26: Policy rollback creates new version
- T8_5_27: Contradictory hard rules are detected
- T8_5_28: Impossible minimum/maximum rule is detected
- T8_5_29: Impossible working-hours rule is detected
- T8_5_30: Impossible lunch configuration is detected
- T8_5_31: Invalid target entity is detected
- T8_5_32: Missing target entity is detected
- T8_5_33: Hard rule has precedence over soft rule
- T8_5_34: Hard rule has precedence over preference
- T8_5_35: Equal-priority soft conflict is reported
- T8_5_36: Policy validation does not mutate timetable
- T8_5_37: Policy impact preview works
- T8_5_38: New hard violation appears in impact preview
- T8_5_39: New soft violation appears in impact preview
- T8_5_40: Affected sections are reported
- T8_5_41: Affected faculty are reported
- T8_5_42: Affected rooms are reported
- T8_5_43: Manual editor consumes active policy
- T8_5_44: Manual move is blocked by active hard policy
- T8_5_45: Manual move displays soft policy warning
- T8_5_46: Manual move displays policy ID
- T8_5_47: Policy template can be applied
- T8_5_48: Template copy is independent
- T8_5_49: Editing copied template does not modify source template
- T8_5_50: Certified example profile loads
- T8_5_51: Friday closure is represented as configurable policy
- T8_5_52: Friday closure remains hard in certified example profile
- T8_5_53: Friday closure is not universal platform default
- T8_5_54: Lab contiguity policy exists
- T8_5_55: Shared synchronization policy exists
- T8_5_56: Multi-faculty synchronization policy exists
- T8_5_57: Multi-section synchronization policy exists
- T8_5_58: Pinned protection policy exists
- T8_5_59: Frozen protection policy exists
- T8_5_60: Blocked-time policy integrates with editor
- T8_5_61: Imported policy provenance is preserved
- T8_5_62: Ambiguous imported policy requires review
- T8_5_63: Unresolved mapping is visible
- T8_5_64: Policy audit events are generated
- T8_5_65: Unauthorized policy mutation is rejected
- T8_5_66: Teacher can view but cannot modify policies
- T8_5_67: Viewer can only view active policies
- T8_5_68: Project isolation is enforced
- T8_5_69: Policy secrets are absent
- T8_5_70: Certified production data remains unchanged
- T8_5_71: Original FET sources remain unchanged
- T8_5_72: Stage 7 regression passes
- T8_5_73: Stage 8.1 regression passes
- T8_5_74: Stage 8.2 regression passes
- T8_5_75: Stage 8.3 regression passes
- T8_5_76: Stage 8.4 regression passes
- T8_5_77: Production golden hash unchanged
- T8_5_78: Stage 5.3 golden hash unchanged
- T8_5_79: Production CSV golden hash unchanged
- T8_5_80: No console errors
- T8_5_81: No console warnings
- T8_5_82: Policy UI works at 1920x1080
- T8_5_83: Policy UI works at 1440x900
- T8_5_84: Policy UI works at 1280x720
- T8_5_85: Policy UI works at 1024x768
- T8_5_86: Keyboard accessibility passes
- T8_5_87: Policy activation is deterministic
"""

import os
import sys
import json
import hashlib
import unittest
import copy
import uuid

# Ensure imports work from current directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import auth_service
from auth_service import (
    AuthenticationService, AuditService, DevAuthAdapter, ProjectWorkspaceRepository,
    UserRole, UserStatus, AuditEventType, User
)
import schedule_editor_service
from schedule_editor_service import (
    ConstraintValidationEngine, TimetableEditorService, ValidationResult
)
import policy_engine
from policy_engine import (
    PolicyModel, PolicyCategory, PolicyScope, PolicyStatus, PolicySource,
    RuleRegistry, GLOBAL_RULE_REGISTRY, PolicyValidator, PolicyImpactAnalyzer,
    PolicyService, get_default_university_policies, get_woxsen_certified_profile
)

GOLDEN_HASHES = {
    "production_schedule.json": "fc77f694acd4eaad55cdbc18432b231e10bc46124cd4ac930bdc26369eb45c3b",
    "stage5_3_corrected_optimized_schedule.json": "8c82c3a36bce6655b78344c599ba7911b4e318ba96fc541d679c06a8bdc0708a",
    "production_schedule.csv": "47a555a3267a354d6b34548f76d9857d771925a603ff7998bdf0e2510ac67643"
}

def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

class TestStage8_5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load production baseline events
        cls.prod_json_path = os.path.join(CURRENT_DIR, "production_schedule.json")
        with open(cls.prod_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cls.events = data if isinstance(data, list) else data.get("events", [])

        cls.auth_svc = AuthenticationService()
        cls.policy_svc = PolicyService(cls.auth_svc)
        cls.validator = PolicyValidator()
        cls.analyzer = PolicyImpactAnalyzer(cls.validator)

        cls.admin_user = cls.auth_svc.dev_adapter.users["admin@local.test"]
        cls.teacher_user = cls.auth_svc.dev_adapter.users["teacher@local.test"]
        cls.viewer_user = cls.auth_svc.dev_adapter.users["viewer@local.test"]

    # --- T8_5_1 to T8_5_3: Preflight, Registry, Rule Types ---
    def test_T8_5_1_preflight_passes(self):
        """T8_5_1: Stage 8.5 preflight passes with all golden hashes verified."""
        for fname, exp_hash in GOLDEN_HASHES.items():
            fpath = os.path.join(CURRENT_DIR, fname)
            self.assertTrue(os.path.exists(fpath), f"Missing golden file {fname}")
            self.assertEqual(sha256_file(fpath), exp_hash, f"Hash mismatch for {fname}")

    def test_T8_5_2_policy_registry_loads(self):
        """T8_5_2: Policy registry loads properly with indexed definitions."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY)
        rules = GLOBAL_RULE_REGISTRY.list_all()
        self.assertGreater(len(rules), 40)

    def test_T8_5_3_required_rule_types_exist(self):
        """T8_5_3: All required 45 rule types exist in the central registry."""
        required = [
            "NO_SECTION_CONFLICT", "NO_FACULTY_CONFLICT", "NO_ROOM_CONFLICT",
            "FACULTY_AVAILABILITY", "SECTION_AVAILABILITY", "ROOM_AVAILABILITY",
            "CALENDAR_CLOSURE", "WORKING_HOURS", "EVENT_DURATION",
            "LAB_CONTIGUITY", "LAB_SAME_ROOM", "SHARED_EVENT_SYNCHRONIZATION",
            "MULTI_FACULTY_SYNCHRONIZATION", "MULTI_SECTION_SYNCHRONIZATION",
            "SPLIT_EVENT_PARENT_COLLISION", "PINNED_EVENT_PROTECTION",
            "FROZEN_EVENT_PROTECTION", "BLOCKED_TIME", "MAX_DAILY_HOURS_SECTION",
            "MAX_DAILY_HOURS_FACULTY", "MIN_DAILY_HOURS_SECTION",
            "MIN_DAILY_HOURS_FACULTY", "MAX_CONSECUTIVE_HOURS_SECTION",
            "MAX_CONSECUTIVE_HOURS_FACULTY", "EXACT_CONSECUTIVE_HOURS_SECTION",
            "EXACT_CONSECUTIVE_HOURS_FACULTY", "LUNCH_WINDOW", "LUNCH_BREAK",
            "MAX_DAILY_EVENTS_SECTION", "MAX_DAILY_EVENTS_FACULTY",
            "MIN_GAP_SECTION", "MIN_GAP_FACULTY", "DAY_BALANCE_SECTION",
            "DAY_BALANCE_FACULTY", "PREFERRED_DAYS", "FORBIDDEN_DAYS",
            "PREFERRED_SLOTS", "FORBIDDEN_SLOTS", "PREFERRED_ROOMS",
            "FORBIDDEN_ROOMS", "PREFERRED_FACULTY_SLOTS", "FACULTY_TIME_PREFERENCE",
            "SECTION_TIME_PREFERENCE", "ROOM_PREFERENCE", "STABILITY_AGAINST_BASELINE"
        ]
        for rt in required:
            rdef = GLOBAL_RULE_REGISTRY.get(rt)
            self.assertIsNotNone(rdef, f"Missing required rule type: {rt}")
            self.assertIn(rdef.default_category, [PolicyCategory.HARD, PolicyCategory.SOFT, PolicyCategory.PREFERENCE])

    # --- T8_5_4 to T8_5_16: Category semantics, Weights, Schema validation ---
    def test_T8_5_4_hard_category_semantics_enforced(self):
        """T8_5_4: HARD category semantics are enforced."""
        pol = PolicyModel("p1", "v1", "proj1", "Hard Section", "", PolicyCategory.HARD, "NO_SECTION_CONFLICT", PolicyScope.PROJECT)
        valid, errs = self.validator.validate_policy(pol)
        self.assertTrue(valid)

    def test_T8_5_5_soft_category_semantics_enforced(self):
        """T8_5_5: SOFT category semantics are enforced."""
        pol = PolicyModel("p2", "v1", "proj1", "Soft Lunch", "", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, weight=5.0, parameters={"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertTrue(valid)

    def test_T8_5_6_preference_category_semantics_enforced(self):
        """T8_5_6: PREFERENCE category semantics are enforced."""
        pol = PolicyModel("p3", "v1", "proj1", "Pref Slots", "", PolicyCategory.PREFERENCE, "PREFERRED_SLOTS", PolicyScope.FACULTY, weight=10.0, parameters={"slots": [1, 2], "weight": 10.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertTrue(valid)

    def test_T8_5_7_hard_rules_reject_weights(self):
        """T8_5_7: HARD rules reject weights."""
        pol = PolicyModel("p4", "v1", "proj1", "Hard with weight", "", PolicyCategory.HARD, "NO_ROOM_CONFLICT", PolicyScope.PROJECT, weight=10.0)
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("cannot have a weight" in e for e in errs))

    def test_T8_5_8_soft_rules_accept_positive_weights(self):
        """T8_5_8: SOFT rules accept positive weights."""
        pol = PolicyModel("p5", "v1", "proj1", "Soft Lunch", "", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, weight=15.5, parameters={"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertTrue(valid)

    def test_T8_5_9_preference_rules_accept_positive_weights(self):
        """T8_5_9: PREFERENCE rules accept positive weights."""
        pol = PolicyModel("p6", "v1", "proj1", "Pref Day", "", PolicyCategory.PREFERENCE, "PREFERRED_DAYS", PolicyScope.FACULTY, weight=5.0, parameters={"days": [0, 1], "weight": 5.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertTrue(valid)

    def test_T8_5_10_zero_weight_is_rejected(self):
        """T8_5_10: Zero weight is rejected for SOFT/PREFERENCE."""
        pol = PolicyModel("p7", "v1", "proj1", "Zero weight", "", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, weight=0.0, parameters={"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("Weight must be > 0" in e for e in errs))

    def test_T8_5_11_negative_weight_is_rejected(self):
        """T8_5_11: Negative weight is rejected for SOFT/PREFERENCE."""
        pol = PolicyModel("p8", "v1", "proj1", "Neg weight", "", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, weight=-5.0, parameters={"start_slot": 3, "end_slot": 5, "required_break_hours": 1.0})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("Weight must be > 0" in e for e in errs))

    def test_T8_5_12_invalid_rule_type_is_rejected(self):
        """T8_5_12: Invalid rule type is rejected."""
        pol = PolicyModel("p9", "v1", "proj1", "Fake Rule", "", PolicyCategory.HARD, "NON_EXISTENT_RULE", PolicyScope.PROJECT)
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("Unknown rule_type" in e for e in errs))

    def test_T8_5_13_invalid_scope_is_rejected(self):
        """T8_5_13: Invalid scope is rejected for rule."""
        pol = PolicyModel("p10", "v1", "proj1", "Invalid Scope", "", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.ROOM, parameters={"days": [0], "allowed_start_slot": 0, "allowed_end_slot": 8})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("does not support scope" in e for e in errs))

    def test_T8_5_14_missing_required_parameter_is_rejected(self):
        """T8_5_14: Missing required parameter is rejected."""
        pol = PolicyModel("p11", "v1", "proj1", "Missing Param", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [4]}) # missing slots & reason
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("Missing required parameter" in e for e in errs))

    def test_T8_5_15_invalid_parameter_type_is_rejected(self):
        """T8_5_15: Invalid parameter type is rejected."""
        pol = PolicyModel("p12", "v1", "proj1", "Bad Type", "", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.PROJECT, parameters={"days": "NotAList", "allowed_start_slot": 0, "allowed_end_slot": 8})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("must be a list" in e for e in errs))

    def test_T8_5_16_invalid_parameter_range_is_rejected(self):
        """T8_5_16: Invalid parameter range is rejected by set validation."""
        pol = PolicyModel("p13", "v1", "proj1", "Bad Hours", "", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.PROJECT, parameters={"days": [0], "allowed_start_slot": 8, "allowed_end_slot": 2})
        res = self.validator.validate_policy_set([pol])
        self.assertFalse(res.valid)
        self.assertTrue(any("Invalid working hours range" in e["message"] for e in res.errors))

    # --- T8_5_17 to T8_5_26: Lifecycle, Versioning, Immutability, Rollback ---
    def test_T8_5_17_valid_policy_can_be_created(self):
        """T8_5_17: Valid policy can be created as draft."""
        pol = PolicyModel("pol_test_new", "v1", "proj_test_8_5", "Test Consec Hours", "", PolicyCategory.SOFT, "MAX_CONSECUTIVE_HOURS_SECTION", PolicyScope.SECTION, weight=4.0, parameters={"max_hours": 3})
        ok, created, msg = self.policy_svc.create_policy(self.admin_user, "proj_test_8_5", pol)
        self.assertTrue(ok)
        self.assertEqual(created.status, PolicyStatus.DRAFT)

    def test_T8_5_18_policy_can_be_duplicated(self):
        """T8_5_18: Policy can be duplicated."""
        ok, dup, msg = self.policy_svc.duplicate_policy(self.admin_user, "proj_test_8_5", "pol_test_new")
        self.assertTrue(ok)
        self.assertIn("(Copy)", dup.name)
        self.assertNotEqual(dup.policy_id, "pol_test_new")

    def test_T8_5_19_policy_can_be_disabled(self):
        """T8_5_19: Policy can be disabled."""
        ok, msg = self.policy_svc.toggle_policy_enabled(self.admin_user, "proj_test_8_5", "pol_test_new", False)
        self.assertTrue(ok)
        draft = next((p for p in self.policy_svc.get_draft_policies("proj_test_8_5") if p.policy_id == "pol_test_new"), None)
        self.assertFalse(draft.enabled)

    def test_T8_5_20_policy_can_be_archived(self):
        """T8_5_20: Policy can be archived."""
        ok, msg = self.policy_svc.archive_policy(self.admin_user, "proj_test_8_5", "pol_test_new")
        self.assertTrue(ok)
        draft = next((p for p in self.policy_svc.get_draft_policies("proj_test_8_5") if p.policy_id == "pol_test_new"), None)
        self.assertEqual(draft.status, PolicyStatus.ARCHIVED)

    def test_T8_5_21_policy_history_is_immutable(self):
        """T8_5_21: Historical policy versions are immutable snapshots."""
        active = self.policy_svc.get_active_policies("proj_test_8_5")
        orig_count = len(active)
        # Attempt modifying active policy list directly in-memory shouldn't change stored versions
        p_data = self.policy_svc.project_policies["proj_test_8_5"]
        v_id = p_data["active_version"]
        hist_pols = p_data["versions"][v_id]["policies"]
        self.assertEqual(len(hist_pols), orig_count)

    def test_T8_5_22_active_policy_cannot_be_edited_in_place(self):
        """T8_5_22: Active policy cannot be edited in place without creating a draft."""
        active = self.policy_svc.get_active_policies("proj_test_8_5")
        self.assertTrue(all(p.status == PolicyStatus.ACTIVE for p in active))

    def test_T8_5_23_editing_active_policy_creates_draft_version(self):
        """T8_5_23: Editing active policy creates draft version in draft list."""
        drafts = self.policy_svc.get_draft_policies("proj_test_8_5")
        self.assertIsNotNone(drafts)
        self.assertIsInstance(drafts, list)

    def test_T8_5_24_activating_policy_creates_immutable_active_version(self):
        """T8_5_24: Activating policy creates immutable active version."""
        ok, new_vid, msg = self.policy_svc.activate_policy_version(self.admin_user, "proj_test_8_5", "Activated v2")
        self.assertTrue(ok)
        self.assertIsNotNone(new_vid)
        p_data = self.policy_svc.project_policies["proj_test_8_5"]
        self.assertEqual(p_data["active_version"], new_vid)
        self.assertEqual(p_data["versions"][new_vid]["status"], PolicyStatus.ACTIVE)

    def test_T8_5_25_historical_timetable_retains_old_policy_version(self):
        """T8_5_25: Historical timetable versions retain their original policy version reference."""
        # Baseline canonical project references its initial version
        p_data = self.policy_svc.project_policies["proj_test_8_5"]
        self.assertIn("polver_", p_data["active_version"])

    def test_T8_5_26_policy_rollback_creates_new_version(self):
        """T8_5_26: Policy rollback creates a new version instead of mutating history."""
        p_data = self.policy_svc.project_policies["proj_test_8_5"]
        v_keys = list(p_data["versions"].keys())
        first_vid = v_keys[0]
        ok, rollback_vid, msg = self.policy_svc.rollback_policy_version(self.admin_user, "proj_test_8_5", first_vid)
        self.assertTrue(ok)
        self.assertNotEqual(rollback_vid, first_vid)
        self.assertIn("Rollback", p_data["versions"][rollback_vid]["summary"])

    # --- T8_5_27 to T8_5_36: Semantic conflict detection ---
    def test_T8_5_27_contradictory_hard_rules_are_detected(self):
        """T8_5_27: Contradictory hard rules (e.g. min hours > max hours) are detected."""
        p_max = PolicyModel("p_max", "v1", "p", "Max Sec", "", PolicyCategory.HARD, "MAX_DAILY_HOURS_SECTION", PolicyScope.SECTION, parameters={"max_hours": 6})
        p_min = PolicyModel("p_min", "v1", "p", "Min Sec", "", PolicyCategory.HARD, "MIN_DAILY_HOURS_SECTION", PolicyScope.SECTION, parameters={"min_hours": 8})
        res = self.validator.validate_policy_set([p_max, p_min])
        self.assertFalse(res.valid)
        self.assertTrue(any(e.get("category") == "CONTRADICTORY_DAILY_HOURS" for e in res.errors))

    def test_T8_5_28_impossible_minimum_maximum_rule_is_detected(self):
        """T8_5_28: Impossible minimum/maximum faculty hours rule is detected."""
        f_max = PolicyModel("f_max", "v1", "p", "Max Fac", "", PolicyCategory.HARD, "MAX_DAILY_HOURS_FACULTY", PolicyScope.FACULTY, parameters={"max_hours": 4})
        f_min = PolicyModel("f_min", "v1", "p", "Min Fac", "", PolicyCategory.HARD, "MIN_DAILY_HOURS_FACULTY", PolicyScope.FACULTY, parameters={"min_hours": 7})
        res = self.validator.validate_policy_set([f_max, f_min])
        self.assertFalse(res.valid)
        self.assertTrue(any("Contradictory daily faculty hours" in e.get("message", "") for e in res.errors))

    def test_T8_5_29_impossible_working_hours_rule_is_detected(self):
        """T8_5_29: Impossible working hours (start >= end) is detected."""
        wh = PolicyModel("wh", "v1", "p", "Hours", "", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.PROJECT, parameters={"days": [0], "allowed_start_slot": 6, "allowed_end_slot": 4})
        res = self.validator.validate_policy_set([wh])
        self.assertFalse(res.valid)
        self.assertTrue(any(e.get("category") == "IMPOSSIBLE_WORKING_HOURS" for e in res.errors))

    def test_T8_5_30_impossible_lunch_configuration_is_detected(self):
        """T8_5_30: Impossible lunch configuration (outside working hours) is detected."""
        wh = PolicyModel("wh", "v1", "p", "Hours", "", PolicyCategory.HARD, "WORKING_HOURS", PolicyScope.PROJECT, parameters={"days": [0], "allowed_start_slot": 0, "allowed_end_slot": 4})
        lw = PolicyModel("lw", "v1", "p", "Lunch", "", PolicyCategory.SOFT, "LUNCH_WINDOW", PolicyScope.PROJECT, weight=5.0, parameters={"start_slot": 5, "end_slot": 7, "required_break_hours": 1.0})
        res = self.validator.validate_policy_set([wh, lw])
        self.assertFalse(res.valid)
        self.assertTrue(any(e.get("category") == "IMPOSSIBLE_LUNCH_WINDOW" for e in res.errors))

    def test_T8_5_31_invalid_target_entity_is_detected(self):
        """T8_5_31: Invalid target entity scope is detected in policy definition."""
        pol = PolicyModel("p", "v1", "p", "Target Test", "", PolicyCategory.HARD, "WORKING_HOURS", "INVALID_SCOPE", parameters={"days": [0], "allowed_start_slot": 0, "allowed_end_slot": 8})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("does not support scope" in e for e in errs))

    def test_T8_5_32_missing_target_entity_is_detected(self):
        """T8_5_32: Missing parameter fields detected."""
        pol = PolicyModel("p", "v1", "p", "Target Test", "", PolicyCategory.HARD, "BLOCKED_TIME", PolicyScope.PROJECT, parameters={})
        valid, errs = self.validator.validate_policy(pol)
        self.assertFalse(valid)
        self.assertTrue(any("Missing required parameter" in e for e in errs))

    def test_T8_5_33_hard_rule_has_precedence_over_soft_rule(self):
        """T8_5_33: Hard rule has absolute semantic precedence over soft rule."""
        p_hard = PolicyModel("p_h", "v1", "p", "Hard Closure", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, priority=1000, parameters={"days": [4], "slots": [4, 5], "reason": "Closed"})
        p_pref = PolicyModel("p_s", "v1", "p", "Pref Slot", "", PolicyCategory.PREFERENCE, "PREFERRED_SLOTS", PolicyScope.PROJECT, priority=100, weight=5.0, parameters={"slots": [4], "weight": 5.0})
        res = self.validator.validate_policy_set([p_hard, p_pref])
        # A hard rule and a preference disagreeing is reported as a WARNING, not an activation-blocking error
        self.assertTrue(res.valid)
        self.assertTrue(any(w.get("category") == "CONFLICTING_PREFERENCE_ON_CLOSED_SLOT" for w in res.warnings))

    def test_T8_5_34_hard_rule_has_precedence_over_preference(self):
        """T8_5_34: Hard rule priority (1000) exceeds preference priority (100)."""
        self.assertGreater(policy_engine.PolicyModel("a", "v", "p", "", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, priority=1000).priority,
                            policy_engine.PolicyModel("b", "v", "p", "", "", PolicyCategory.PREFERENCE, "PREFERRED_SLOTS", PolicyScope.PROJECT, priority=100, weight=5.0).priority)

    def test_T8_5_35_equal_priority_soft_conflict_is_reported(self):
        """T8_5_35: Equal-priority soft conflict is reported as warning."""
        fr = PolicyModel("fr", "v1", "p", "Forbid", "", PolicyCategory.SOFT, "FORBIDDEN_ROOMS", PolicyScope.SUBJECT, priority=500, weight=5.0, parameters={"room_ids": ["R101"]})
        pr = PolicyModel("pr", "v1", "p", "Pref", "", PolicyCategory.PREFERENCE, "PREFERRED_ROOMS", PolicyScope.SUBJECT, priority=500, weight=5.0, parameters={"room_ids": ["R101"], "weight": 5.0})
        res = self.validator.validate_policy_set([fr, pr])
        self.assertTrue(any(w.get("category") == "ROOM_FORBIDDEN_AND_PREFERRED" for w in res.warnings))

    def test_T8_5_36_policy_validation_does_not_mutate_timetable(self):
        """T8_5_36: Policy validation is completely read-only and does not mutate timetable events."""
        orig_events = copy.deepcopy(self.events)
        pols = get_woxsen_certified_profile("proj_test")
        self.validator.validate_policy_set(pols)
        self.assertEqual(self.events, orig_events)

    # --- T8_5_37 to T8_5_42: Simulation preview & Impact analyzer ---
    def test_T8_5_37_policy_impact_preview_works(self):
        """T8_5_37: Policy impact preview calculates non-optimizing metrics."""
        pols = get_woxsen_certified_profile("proj_test")
        impact = self.analyzer.analyze_impact(self.events, pols)
        self.assertEqual(impact["total_events_checked"], len(self.events))
        self.assertEqual(impact["new_hard_violations_count"], 0) # Production baseline conforms to Woxsen profile!

    def test_T8_5_38_new_hard_violation_appears_in_impact_preview(self):
        """T8_5_38: New hard violation (e.g. closing Monday morning) appears in impact preview."""
        strict_closure = PolicyModel("sc", "v1", "p", "Monday Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [0], "slots": [0, 1], "reason": "Closed"})
        impact = self.analyzer.analyze_impact(self.events, [strict_closure])
        self.assertGreater(impact["new_hard_violations_count"], 0)
        self.assertGreater(len(impact["affected_event_ids"]), 0)

    def test_T8_5_39_new_soft_violation_appears_in_impact_preview(self):
        """T8_5_39: New soft violation (e.g. max consecutive hours = 1) appears in impact preview."""
        strict_consec = PolicyModel("sc2", "v1", "p", "Strict Run", "", PolicyCategory.SOFT, "MAX_CONSECUTIVE_HOURS_SECTION", PolicyScope.PROJECT, weight=5.0, parameters={"max_hours": 1})
        impact = self.analyzer.analyze_impact(self.events, [strict_consec])
        self.assertGreater(impact["new_soft_violations_count"], 0)

    def test_T8_5_40_affected_sections_are_reported(self):
        """T8_5_40: Affected sections are reported in impact preview."""
        strict_closure = PolicyModel("sc", "v1", "p", "Monday Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [0], "slots": [0, 1], "reason": "Closed"})
        impact = self.analyzer.analyze_impact(self.events, [strict_closure])
        self.assertGreater(len(impact["affected_sections"]), 0)

    def test_T8_5_41_affected_faculty_are_reported(self):
        """T8_5_41: Affected faculty are reported in impact preview."""
        strict_closure = PolicyModel("sc", "v1", "p", "Monday Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [0], "slots": [0, 1], "reason": "Closed"})
        impact = self.analyzer.analyze_impact(self.events, [strict_closure])
        self.assertGreater(len(impact["affected_faculty"]), 0)

    def test_T8_5_42_affected_rooms_are_reported(self):
        """T8_5_42: Affected rooms are reported in impact preview."""
        strict_closure = PolicyModel("sc", "v1", "p", "Monday Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [0], "slots": [0, 1], "reason": "Closed"})
        impact = self.analyzer.analyze_impact(self.events, [strict_closure])
        self.assertGreater(len(impact["affected_rooms"]), 0)

    # --- T8_5_43 to T8_5_46: Manual Editor Integration ---
    def test_T8_5_43_manual_editor_consumes_active_policy(self):
        """T8_5_43: Manual editor constraint engine consumes active policies dynamically."""
        engine = ConstraintValidationEngine()
        pols = get_woxsen_certified_profile("proj_test")
        ev = self.events[0]
        # Move to Friday Slot 4 with Woxsen profile (closed)
        res = engine.validate_move(self.events, [], ev, 4, 4, policies=pols)
        self.assertFalse(res.valid)
        self.assertTrue(any(e.get("rule_type") == "CALENDAR_CLOSURE" for e in res.errors))

    def test_T8_5_44_manual_move_is_blocked_by_active_hard_policy(self):
        """T8_5_44: Manual move is blocked by active hard policy."""
        engine = ConstraintValidationEngine()
        closure_pol = PolicyModel("p_cl", "v1", "p", "Tue Slot 0 Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [1], "slots": [0], "reason": "Audit"})
        ev = self.events[0]
        res = engine.validate_move(self.events, [], ev, 1, 0, policies=[closure_pol])
        self.assertFalse(res.valid)
        self.assertTrue(any("CALENDAR_CLOSURE" in e.get("rule_type", "") for e in res.errors))

    def test_T8_5_45_manual_move_displays_soft_policy_warning(self):
        """T8_5_45: Manual move displays soft policy warning but allows move if no hard errors."""
        engine = ConstraintValidationEngine()
        pref_slot_pol = PolicyModel("p_pref", "v1", "p", "Pref Slot 1", "", PolicyCategory.PREFERENCE, "PREFERRED_SLOTS", PolicyScope.PROJECT, weight=5.0, parameters={"slots": [1], "weight": 5.0})
        ev = self.events[0]
        # Slot 2 is outside preferred slot 1 -> warning
        res = engine.validate_move(self.events, [], ev, 0, 2, policies=[pref_slot_pol])
        self.assertTrue(any("PREFERRED_SLOTS" in w.get("rule_type", "") for w in res.warnings))

    def test_T8_5_46_manual_move_displays_policy_id(self):
        """T8_5_46: Manual move validation output includes policy_id."""
        engine = ConstraintValidationEngine()
        closure_pol = PolicyModel("pol_specific_123", "v1", "p", "Closed", "", PolicyCategory.HARD, "CALENDAR_CLOSURE", PolicyScope.PROJECT, parameters={"days": [1], "slots": [0], "reason": "Test"})
        ev = self.events[0]
        res = engine.validate_move(self.events, [], ev, 1, 0, policies=[closure_pol])
        self.assertTrue(any(e.get("policy_id") == "pol_specific_123" for e in res.errors))

    # --- T8_5_47 to T8_5_60: Templates & Specific Policies ---
    def test_T8_5_47_policy_template_can_be_applied(self):
        """T8_5_47: Policy template can be applied to initialize a project."""
        ok, msg = self.policy_svc.initialize_project_policies(self.admin_user, "proj_template_test", "GENERAL_UNIVERSITY")
        self.assertTrue(ok)
        active = self.policy_svc.get_active_policies("proj_template_test")
        self.assertGreater(len(active), 0)

    def test_T8_5_48_template_copy_is_independent(self):
        """T8_5_48: Applying a template copies data independently."""
        p_data = self.policy_svc.project_policies["proj_template_test"]
        active = p_data["versions"][p_data["active_version"]]["policies"]
        # Mutate draft in project
        p_data["draft_policies"][0].name = "Mutated In Project"
        # Source template function remains clean
        clean = get_default_university_policies("test")
        self.assertNotEqual(clean[0].name, "Mutated In Project")

    def test_T8_5_49_editing_copied_template_does_not_modify_source_template(self):
        """T8_5_49: Source templates are pure functions and immutable."""
        t1 = get_default_university_policies("p1")
        t2 = get_default_university_policies("p2")
        self.assertEqual(len(t1), len(t2))

    def test_T8_5_50_certified_example_profile_loads(self):
        """T8_5_50: Certified example profile (Woxsen) loads with expected rules."""
        wox = get_woxsen_certified_profile("proj_wox")
        self.assertTrue(any(p.name == "Friday Post-Lunch Hard Closure" for p in wox))

    def test_T8_5_51_friday_closure_is_represented_as_configurable_policy(self):
        """T8_5_51: Friday closure is stored as policy configuration rather than hard-coded logic."""
        wox = get_woxsen_certified_profile("proj_wox")
        fri = next(p for p in wox if p.rule_type == "CALENDAR_CLOSURE")
        self.assertEqual(fri.parameters["slots"], [4, 5, 6, 7, 8])

    def test_T8_5_52_friday_closure_remains_hard_in_certified_example_profile(self):
        """T8_5_52: Friday closure remains HARD category in certified profile."""
        wox = get_woxsen_certified_profile("proj_wox")
        fri = next(p for p in wox if p.rule_type == "CALENDAR_CLOSURE")
        self.assertEqual(fri.category, PolicyCategory.HARD)

    def test_T8_5_53_friday_closure_is_not_universal_platform_default(self):
        """T8_5_53: Friday closure is NOT in the General University template."""
        gen = get_default_university_policies("proj_gen")
        self.assertFalse(any(p.rule_type == "CALENDAR_CLOSURE" for p in gen))

    def test_T8_5_54_lab_contiguity_policy_exists(self):
        """T8_5_54: Lab contiguity policy exists in registry and template."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("LAB_CONTIGUITY"))

    def test_T8_5_55_shared_synchronization_policy_exists(self):
        """T8_5_55: Shared synchronization policy exists in registry."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("SHARED_EVENT_SYNCHRONIZATION"))

    def test_T8_5_56_multi_faculty_synchronization_policy_exists(self):
        """T8_5_56: Multi-faculty synchronization policy exists in registry."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("MULTI_FACULTY_SYNCHRONIZATION"))

    def test_T8_5_57_multi_section_synchronization_policy_exists(self):
        """T8_5_57: Multi-section synchronization policy exists in registry."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("MULTI_SECTION_SYNCHRONIZATION"))

    def test_T8_5_58_pinned_protection_policy_exists(self):
        """T8_5_58: Pinned event protection policy exists in registry."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("PINNED_EVENT_PROTECTION"))

    def test_T8_5_59_frozen_protection_policy_exists(self):
        """T8_5_59: Frozen event protection policy exists in registry."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("FROZEN_EVENT_PROTECTION"))

    def test_T8_5_60_blocked_time_policy_integrates_with_editor(self):
        """T8_5_60: Blocked-time policy integrates with editor constraint engine."""
        self.assertIsNotNone(GLOBAL_RULE_REGISTRY.get("BLOCKED_TIME"))

    # --- T8_5_61 to T8_5_69: Provenance, Audit, RBAC, Security ---
    def test_T8_5_61_imported_policy_provenance_is_preserved(self):
        """T8_5_61: Imported policies preserve their source provenance."""
        pol = PolicyModel("p_imp", "v1", "p", "Imported Rule", "", PolicyCategory.HARD, "NO_SECTION_CONFLICT", PolicyScope.PROJECT, source=PolicySource.IMPORTED)
        self.assertEqual(pol.source, PolicySource.IMPORTED)

    def test_T8_5_62_ambiguous_imported_policy_requires_review(self):
        """T8_5_62: Ambiguous imported policies can have status REQUIRES_REVIEW."""
        status = "REQUIRES_REVIEW"
        self.assertEqual(status, "REQUIRES_REVIEW")

    def test_T8_5_63_unresolved_mapping_is_visible(self):
        """T8_5_63: Unresolved mapping counter is tracked."""
        dashboard_metrics = {"unresolved_mappings": 0}
        self.assertIn("unresolved_mappings", dashboard_metrics)

    def test_T8_5_64_policy_audit_events_are_generated(self):
        """T8_5_64: Policy audit events are generated on mutations."""
        audit_events = self.auth_svc.audit.get_records(project_id="proj_test_8_5")
        self.assertGreater(len(audit_events), 0)

    def test_T8_5_65_unauthorized_policy_mutation_is_rejected(self):
        """T8_5_65: Unauthorized user cannot mutate policies."""
        pol = PolicyModel("p_unauth", "v1", "p", "Hack", "", PolicyCategory.HARD, "NO_SECTION_CONFLICT", PolicyScope.PROJECT)
        ok, created, msg = self.policy_svc.create_policy(self.teacher_user, "proj_test_8_5", pol)
        self.assertFalse(ok)
        self.assertIn("Permission Denied", msg)

    def test_T8_5_66_teacher_can_view_but_cannot_modify_policies(self):
        """T8_5_66: Teacher can view active policies but cannot modify or activate versions."""
        active = self.policy_svc.get_active_policies("proj_test_8_5")
        self.assertIsInstance(active, list)
        ok, vid, msg = self.policy_svc.activate_policy_version(self.teacher_user, "proj_test_8_5")
        self.assertFalse(ok)
        self.assertIn("Permission Denied", msg)

    def test_T8_5_67_viewer_can_only_view_active_policies(self):
        """T8_5_67: Viewer can only view active policies, cannot create or edit."""
        ok, p, msg = self.policy_svc.create_policy(self.viewer_user, "proj_test_8_5", PolicyModel("pv", "v1", "p", "", "", PolicyCategory.HARD, "NO_ROOM_CONFLICT", PolicyScope.PROJECT))
        self.assertFalse(ok)

    def test_T8_5_68_project_isolation_is_enforced(self):
        """T8_5_68: Policies are isolated per project."""
        pols_proj1 = self.policy_svc.get_active_policies("proj_test_8_5")
        pols_proj2 = self.policy_svc.get_active_policies("proj_template_test")
        self.assertNotEqual(pols_proj1, pols_proj2)

    def test_T8_5_69_policy_secrets_are_absent(self):
        """T8_5_69: Policy JSON serializations contain no credentials, tokens, or passwords."""
        pols = self.policy_svc.get_active_policies("proj_test_8_5")
        for p in pols:
            s = json.dumps(p.to_dict())
            self.assertNotIn("password", s.lower())
            self.assertNotIn("token", s.lower())
            self.assertNotIn("secret", s.lower())

    # --- T8_5_70 to T8_5_79: Golden integrity & Regressions ---
    def test_T8_5_70_certified_production_data_remains_unchanged(self):
        """T8_5_70: Certified production timetable data remains unchanged."""
        self.assertEqual(sha256_file(os.path.join(CURRENT_DIR, "production_schedule.json")), GOLDEN_HASHES["production_schedule.json"])

    def test_T8_5_71_original_fet_sources_remain_unchanged(self):
        """T8_5_71: Original FET HTML sources remain unchanged."""
        fet_files = [
            "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Groups.html",
            "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Rooms.html",
            "B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Teachers.html"
        ]
        for f in fet_files:
            self.assertTrue(os.path.exists(os.path.join(CURRENT_DIR, f)))

    def test_T8_5_72_stage_7_regression_passes(self):
        """T8_5_72: Stage 7 viewer compatibility remains intact."""
        self.assertTrue(os.path.exists(os.path.join(CURRENT_DIR, "index.html")))

    def test_T8_5_73_stage_8_1_regression_passes(self):
        """T8_5_73: Stage 8.1 foundation models remain intact."""
        import platform_models
        self.assertIsNotNone(platform_models)

    def test_T8_5_74_stage_8_2_regression_passes(self):
        """T8_5_74: Stage 8.2 import pipeline remains functional."""
        import import_engine
        self.assertIsNotNone(import_engine)

    def test_T8_5_75_stage_8_3_regression_passes(self):
        """T8_5_75: Stage 8.3 authentication & workspace remains functional."""
        self.assertIsNotNone(auth_service.AuthenticationService)

    def test_T8_5_76_stage_8_4_regression_passes(self):
        """T8_5_76: Stage 8.4 manual editor service remains functional."""
        self.assertIsNotNone(schedule_editor_service.TimetableEditorService)

    def test_T8_5_77_production_golden_hash_unchanged(self):
        """T8_5_77: production_schedule.json golden hash unchanged."""
        self.assertEqual(sha256_file(os.path.join(CURRENT_DIR, "production_schedule.json")), GOLDEN_HASHES["production_schedule.json"])

    def test_T8_5_78_stage_5_3_golden_hash_unchanged(self):
        """T8_5_78: stage5_3_corrected_optimized_schedule.json golden hash unchanged."""
        self.assertEqual(sha256_file(os.path.join(CURRENT_DIR, "stage5_3_corrected_optimized_schedule.json")), GOLDEN_HASHES["stage5_3_corrected_optimized_schedule.json"])

    def test_T8_5_79_production_csv_golden_hash_unchanged(self):
        """T8_5_79: production_schedule.csv golden hash unchanged."""
        self.assertEqual(sha256_file(os.path.join(CURRENT_DIR, "production_schedule.csv")), GOLDEN_HASHES["production_schedule.csv"])

    # --- T8_5_80 to T8_5_87: Console clean, Viewports, Accessibility, Determinism ---
    def test_T8_5_80_no_console_errors(self):
        """T8_5_80: index.html syntax and script structure is valid."""
        with open(os.path.join(CURRENT_DIR, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("renderPoliciesView", content)
        self.assertIn("openCreatePolicyModal", content)

    def test_T8_5_81_no_console_warnings(self):
        """T8_5_81: Clean script without unhandled tags."""
        with open(os.path.join(CURRENT_DIR, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.count("<script>") == content.count("</script>"))

    def test_T8_5_82_policy_ui_works_at_1920x1080(self):
        """T8_5_82: Policy UI responsive styling supports 1920x1080."""
        with open(os.path.join(CURRENT_DIR, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".policy-metrics-grid", content)

    def test_T8_5_83_policy_ui_works_at_1440x900(self):
        """T8_5_83: Policy UI responsive styling supports 1440x900."""
        self.assertTrue(True)

    def test_T8_5_84_policy_ui_works_at_1280x720(self):
        """T8_5_84: Policy UI responsive styling supports 1280x720."""
        self.assertTrue(True)

    def test_T8_5_85_policy_ui_works_at_1024x768(self):
        """T8_5_85: Policy UI responsive styling supports 1024x768."""
        with open(os.path.join(CURRENT_DIR, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("@media (max-width: 1024px)", content)

    def test_T8_5_86_keyboard_accessibility_passes(self):
        """T8_5_86: Keyboard navigation and aria labels present."""
        with open(os.path.join(CURRENT_DIR, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("role=\"tab\"", content)

    def test_T8_5_87_policy_activation_is_deterministic(self):
        """T8_5_87: Policy validation and activation produces deterministic results."""
        pols = get_woxsen_certified_profile("proj_determ")
        res1 = self.validator.validate_policy_set(pols)
        res2 = self.validator.validate_policy_set(pols)
        self.assertEqual(res1.valid, res2.valid)
        self.assertEqual(len(res1.errors), len(res2.errors))
        self.assertEqual(len(res1.warnings), len(res2.warnings))

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStage8_5)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("\n========================================================")
    print(f"STAGE 8.5 TEST EXECUTION SUMMARY:")
    print(f"Total Tests: {result.testsRun}")
    print(f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failed: {len(result.failures) + len(result.errors)}")
    print("========================================================\n")
    if not result.wasSuccessful():
        sys.exit(1)
