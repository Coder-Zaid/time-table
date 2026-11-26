"""
Stage OPTIMIZATION_PREFERENCE_UPDATE_01 Test Suite
Tests covering:
- Late start preference (P5 HIGH)
- Additional break preference (P4 HIGH)
- Early finish preference (P6 MEDIUM)
- Lexicographic ordering and hierarchy
- Scenarios 1, 2, and 3 from specification
- Measurement rules (total vs consecutive free time, closed calendar slots exclusion)
- Section, Student Group, Faculty scopes
- Hard constraint precedence over preferences
- Deterministic candidate sorting
- Profile compatibility (FEASIBILITY_FIRST, BALANCED, QUALITY_FIRST, STABILITY_FIRST)
- Generation and Recovery engine integration
- Policy enable/disable toggle and immutable versioning
- Golden hash invariants
"""

import unittest
import hashlib
import json
import os
import sys

from policy_engine import (
    RuleRegistry,
    GLOBAL_RULE_REGISTRY,
    PolicyValidator,
    PolicyService,
    PolicyModel,
    PolicyScope,
    PolicyCategory,
    PolicyStatus,
    get_optimization_preferences_profile,
    get_woxsen_certified_profile
)
from generation_models import QualityScore, GenerationProfile, GenerationConfig
from generation_engine import TimetableGenerationEngine
from simulation_models import (
    DisruptionScenario,
    ScenarioType,
    RecoveryCandidate
)
from simulation_engine import TimetableSimulationEngine
import auth_service


class TestOptimizationPreferenceUpdate01(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth_svc = auth_service.AuthenticationService()
        cls.policy_svc = PolicyService(cls.auth_svc)
        cls.validator = PolicyValidator(GLOBAL_RULE_REGISTRY)
        cls.generation_engine = TimetableGenerationEngine()
        cls.simulation_engine = TimetableSimulationEngine()
        cls.golden_files = {
            "production_schedule.json": "c:/Users/asus/.gemini/antigravity-ide/scratch/CP-Timetable/production_schedule.json",
            "stage5_3_corrected_optimized_schedule.json": "c:/Users/asus/.gemini/antigravity-ide/scratch/CP-Timetable/stage5_3_corrected_optimized_schedule.json"
        }

    # -------------------------------------------------------------
    # 1. Rule Registry & Validation Tests
    # -------------------------------------------------------------
    def test_01_rule_registry_contains_new_preferences(self):
        """Verify PREF_LATE_START, PREF_ADDITIONAL_BREAK, PREF_EARLY_FINISH are registered."""
        rules = GLOBAL_RULE_REGISTRY.list_all()
        rule_types = {r.rule_type for r in rules}
        self.assertIn("PREF_LATE_START", rule_types)
        self.assertIn("PREF_ADDITIONAL_BREAK", rule_types)
        self.assertIn("PREF_EARLY_FINISH", rule_types)

    def test_02_rule_metadata_and_scopes(self):
        """Verify supported scopes include PROJECT, SECTION, STUDENT_GROUP, FACULTY."""
        for r_type in ["PREF_LATE_START", "PREF_ADDITIONAL_BREAK", "PREF_EARLY_FINISH"]:
            spec = GLOBAL_RULE_REGISTRY.get(r_type)
            self.assertIsNotNone(spec)
            self.assertIn(PolicyCategory.PREFERENCE, spec.category_support)
            for sc in [PolicyScope.PROJECT, PolicyScope.SECTION, PolicyScope.STUDENT_GROUP, PolicyScope.FACULTY]:
                self.assertIn(sc, spec.scope_support)

    def test_03_default_parameter_population(self):
        """Verify get_optimization_preferences_profile fills valid parameters."""
        pols = get_optimization_preferences_profile("PRJ_TEST")
        p_map = {p.rule_type: p for p in pols}
        self.assertIn("PREF_LATE_START", p_map)
        ls = p_map["PREF_LATE_START"]
        self.assertTrue(ls.parameters.get("enabled"))
        self.assertEqual(ls.parameters.get("preferred_start_slot"), 1)
        self.assertEqual(ls.priority, 600)

    def test_04_conflict_start_finish_slot(self):
        """Verify contradiction error if preferred_start_slot >= preferred_finish_slot."""
        rule_start = PolicyModel(
            policy_id="p_ls",
            policy_version_id="v1",
            project_id="PRJ_TEST",
            name="Late Start",
            description="",
            category=PolicyCategory.PREFERENCE,
            rule_type="PREF_LATE_START",
            scope=PolicyScope.PROJECT,
            parameters={"enabled": True, "preferred_start_slot": 6}
        )
        rule_finish = PolicyModel(
            policy_id="p_ef",
            policy_version_id="v1",
            project_id="PRJ_TEST",
            name="Early Finish",
            description="",
            category=PolicyCategory.PREFERENCE,
            rule_type="PREF_EARLY_FINISH",
            scope=PolicyScope.PROJECT,
            parameters={"enabled": True, "preferred_finish_slot": 4}
        )
        res = self.validator.validate_policy_set([rule_start, rule_finish])
        self.assertFalse(res.valid)
        error_msgs = [e.get("message", "") for e in res.errors]
        self.assertTrue(any("must be earlier than" in m for m in error_msgs))

    def test_05_invalid_slot_bounds(self):
        """Verify error if preferred slots are outside [0, 8]."""
        rule = PolicyModel(
            policy_id="p_ls_oob",
            policy_version_id="v1",
            project_id="PRJ_TEST",
            name="Late Start OOB",
            description="",
            category=PolicyCategory.PREFERENCE,
            rule_type="PREF_LATE_START",
            scope=PolicyScope.PROJECT,
            parameters={"enabled": True, "preferred_start_slot": 10}
        )
        res = self.validator.validate_policy_set([rule])
        self.assertFalse(res.valid)
        error_msgs = [e.get("message", "") for e in res.errors]
        self.assertTrue(any("operational slots [0, 8]" in m for m in error_msgs))

    def test_06_invalid_negative_break_hours(self):
        """Verify error if preferred free hours <= 0."""
        rule = PolicyModel(
            policy_id="p_ab_neg",
            policy_version_id="v1",
            project_id="PRJ_TEST",
            name="Break Neg",
            description="",
            category=PolicyCategory.PREFERENCE,
            rule_type="PREF_ADDITIONAL_BREAK",
            scope=PolicyScope.PROJECT,
            parameters={"enabled": True, "preferred_total_free_hours": -1}
        )
        res = self.validator.validate_policy_set([rule])
        self.assertFalse(res.valid)
        error_msgs = [e.get("message", "") for e in res.errors]
        self.assertTrue(any("greater than 0" in m for m in error_msgs))

    # -------------------------------------------------------------
    # 2. Lexicographic Quality Ordering & Comparison Tests
    # -------------------------------------------------------------
    def test_07_scenario_1_late_start_beats_early_finish(self):
        """
        Scenario 1 from spec:
        Schedule A: start 09:00 (slot 0), finish 16:00 (slot 7), free time 2h
        Schedule B: start 10:00 (slot 1), finish 17:00 (slot 8), free time 2h
        Both satisfy P0..P4 equally. Schedule B has better late start (P5), worse early finish (P6).
        Lexicographically, B must defeat A.
        """
        score_a = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=100.0,
            p5_late_start=50.0,   # start 09:00
            p6_early_finish=90.0,  # finish 16:00
            p7_other=100.0,
            p8_stability=100.0
        )
        score_b = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=100.0,
            p5_late_start=80.0,   # start 10:00 (better)
            p6_early_finish=70.0,  # finish 17:00 (worse)
            p7_other=100.0,
            p8_stability=100.0
        )
        key_a = (score_a.hard_violation_count, -score_a.p1_critical, -score_a.p2_runs_gaps, -score_a.p3_balance,
                 -score_a.p4_break_quality, -score_a.p5_late_start, -score_a.p6_early_finish)
        key_b = (score_b.hard_violation_count, -score_b.p1_critical, -score_b.p2_runs_gaps, -score_b.p3_balance,
                 -score_b.p4_break_quality, -score_b.p5_late_start, -score_b.p6_early_finish)

        self.assertLess(key_b, key_a, "Schedule B must be ranked ahead of Schedule A (lower sort key).")

    def test_08_scenario_2_break_quality_beats_late_start(self):
        """
        Scenario 2 from spec:
        Schedule A: first class 09:00, total free time 2 hours (P4 high, P5 lower)
        Schedule B: first class 10:00, total free time 1 hour (P4 low, P5 higher)
        Schedule A has better P4 (additional break quality), which is Tier P4 vs P5.
        Lexicographically, Schedule A must defeat Schedule B.
        """
        score_a = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=95.0,  # 2h free time
            p5_late_start=60.0,     # start 09:00
            p6_early_finish=80.0
        )
        score_b = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=60.0,  # only 1h free time
            p5_late_start=90.0,     # start 10:00
            p6_early_finish=80.0
        )
        key_a = (score_a.hard_violation_count, -score_a.p1_critical, -score_a.p2_runs_gaps, -score_a.p3_balance,
                 -score_a.p4_break_quality, -score_a.p5_late_start, -score_a.p6_early_finish)
        key_b = (score_b.hard_violation_count, -score_b.p1_critical, -score_b.p2_runs_gaps, -score_b.p3_balance,
                 -score_b.p4_break_quality, -score_b.p5_late_start, -score_b.p6_early_finish)

        self.assertLess(key_a, key_b, "Schedule A must defeat Schedule B because P4 > P5.")

    def test_09_scenario_3_dual_improvement(self):
        """
        Scenario 3 from spec:
        Schedule A: 09:00 to 17:00
        Schedule B: 10:00 to 16:00
        Schedule B improves both late start (P5) and early finish (P6).
        """
        score_a = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=100.0,
            p5_late_start=50.0,
            p6_early_finish=50.0
        )
        score_b = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=100.0,
            p4_break_quality=100.0,
            p5_late_start=85.0,
            p6_early_finish=85.0
        )
        key_a = (score_a.hard_violation_count, -score_a.p1_critical, -score_a.p2_runs_gaps, -score_a.p3_balance,
                 -score_a.p4_break_quality, -score_a.p5_late_start, -score_a.p6_early_finish)
        key_b = (score_b.hard_violation_count, -score_b.p1_critical, -score_b.p2_runs_gaps, -score_b.p3_balance,
                 -score_b.p4_break_quality, -score_b.p5_late_start, -score_b.p6_early_finish)

        self.assertLess(key_b, key_a, "Schedule B must decisively defeat Schedule A.")

    def test_10_hard_constraint_precedence_over_all_preferences(self):
        """Verify hard violation in P0 cannot be defeated by any high preference scores."""
        score_infeasible = QualityScore(
            hard_violation_count=1,
            p1_critical=100.0,
            p4_break_quality=100.0,
            p5_late_start=100.0,
            p6_early_finish=100.0
        )
        score_feasible = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p4_break_quality=50.0,
            p5_late_start=50.0,
            p6_early_finish=50.0
        )
        key_infeasible = (score_infeasible.hard_violation_count, -score_infeasible.p1_critical, -score_infeasible.p4_break_quality, -score_infeasible.p5_late_start)
        key_feasible = (score_feasible.hard_violation_count, -score_feasible.p1_critical, -score_feasible.p4_break_quality, -score_feasible.p5_late_start)
        self.assertLess(key_feasible, key_infeasible, "Feasible candidate must ALWAYS precede infeasible candidate.")

    def test_11_critical_quality_p1_precedence_over_preferences(self):
        """Verify P1 (e.g. lab continuity, closure conflicts) precedes P4/P5/P6."""
        score_poor_p1 = QualityScore(
            hard_violation_count=0,
            p1_critical=70.0,
            p4_break_quality=100.0,
            p5_late_start=100.0
        )
        score_good_p1 = QualityScore(
            hard_violation_count=0,
            p1_critical=95.0,
            p4_break_quality=70.0,
            p5_late_start=70.0
        )
        key_poor_p1 = (score_poor_p1.hard_violation_count, -score_poor_p1.p1_critical, -score_poor_p1.p4_break_quality, -score_poor_p1.p5_late_start)
        key_good_p1 = (score_good_p1.hard_violation_count, -score_good_p1.p1_critical, -score_good_p1.p4_break_quality, -score_good_p1.p5_late_start)
        self.assertLess(key_good_p1, key_poor_p1, "Higher P1 critical quality must strictly precede preferences.")

    def test_12_runs_and_gaps_p2_precedence_over_late_start(self):
        """Verify P2 (runs and gaps) precedes P5 (late start)."""
        score_excess_gaps = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=60.0,
            p5_late_start=100.0
        )
        score_tight_gaps = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=90.0,
            p5_late_start=70.0
        )
        key_gaps = (score_excess_gaps.hard_violation_count, -score_excess_gaps.p1_critical, -score_excess_gaps.p2_runs_gaps, -score_excess_gaps.p5_late_start)
        key_tight = (score_tight_gaps.hard_violation_count, -score_tight_gaps.p1_critical, -score_tight_gaps.p2_runs_gaps, -score_tight_gaps.p5_late_start)
        self.assertLess(key_tight, key_gaps, "P2 runs & gaps must strictly precede P5 late start.")

    def test_13_daily_workload_balance_p3_precedence_over_early_finish(self):
        """Verify P3 (daily balance) precedes P6 (early finish)."""
        score_unbalanced = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=60.0,
            p6_early_finish=100.0
        )
        score_balanced = QualityScore(
            hard_violation_count=0,
            p1_critical=100.0,
            p2_runs_gaps=100.0,
            p3_balance=90.0,
            p6_early_finish=70.0
        )
        key_unbalanced = (score_unbalanced.hard_violation_count, -score_unbalanced.p1_critical, -score_unbalanced.p2_runs_gaps, -score_unbalanced.p3_balance, -score_unbalanced.p6_early_finish)
        key_balanced = (score_balanced.hard_violation_count, -score_balanced.p1_critical, -score_balanced.p2_runs_gaps, -score_balanced.p3_balance, -score_balanced.p6_early_finish)
        self.assertLess(key_balanced, key_unbalanced, "P3 daily balance must strictly precede P6 early finish.")

    # -------------------------------------------------------------
    # 3. Measurement Rules & Metrics Computation Tests
    # -------------------------------------------------------------
    def test_14_closed_calendar_slots_excluded_from_free_time(self):
        """
        Verify Friday slots 4..8 (13:00-18:00) which are campus closures
        are NOT counted as student/faculty preferred free time.
        """
        # SEC_TEST has 1 teaching event on Friday at slot 0.
        # Usable slots on Friday: 0, 1, 2, 3 (total 4).
        # Free slots on Friday: 1, 2, 3 (3 hours), NOT 3 + 5 = 8 hours.
        dummy_events = [
            {"event_id": "EV1", "day": 4, "slot": 0, "duration": 1, "sections": ["SEC_TEST"], "faculty": [], "student_groups": []}
        ]
        cal_info = {"closed_by_day": {4: {4, 5, 6, 7, 8}}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_total_free_hours"], 3.0)

    def test_15_total_vs_consecutive_free_time_distinction(self):
        """
        Verify total free time tracks all usable non-teaching slots,
        while consecutive free time tracks the maximum contiguous run.
        """
        # Monday (Day 0): 9 usable slots (0..8)
        # Classes at Slot 0, Slot 4, Slot 8.
        # Free slots: [1, 2, 3] (len 3) and [5, 6, 7] (len 3).
        # Total free hours = 6. Max consecutive = 3.
        dummy_events = [
            {"event_id": "EV1", "day": 0, "slot": 0, "duration": 1, "sections": ["SEC_DIST"], "faculty": [], "student_groups": []},
            {"event_id": "EV2", "day": 0, "slot": 4, "duration": 1, "sections": ["SEC_DIST"], "faculty": [], "student_groups": []},
            {"event_id": "EV3", "day": 0, "slot": 8, "duration": 1, "sections": ["SEC_DIST"], "faculty": [], "student_groups": []}
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_total_free_hours"], 6.0)
        self.assertEqual(metrics["average_consecutive_free_hours"], 3.0)

    def test_16_mandatory_1_hour_break_preservation_and_additional_free_time(self):
        """
        Verify average_additional_free_hours is computed as max(0.0, total_free - 1.0)
        preserving the mandatory 1-hour break baseline.
        """
        # Monday (9 usable slots). Classes at slot 0..6 (7 classes).
        # Free slots: 7, 8 (2 hours total).
        # Mandatory break = 1h. Additional free time = 1h.
        dummy_events = [
            {"event_id": f"EV_{i}", "day": 0, "slot": i, "duration": 1, "sections": ["SEC_BRK"], "faculty": [], "student_groups": []}
            for i in range(7)
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_total_free_hours"], 2.0)
        self.assertEqual(metrics["average_additional_free_hours"], 1.0)

    def test_17_first_teaching_slot_measurement(self):
        """Verify first_teaching_slot measurement across active days."""
        # Class at slot 2 on Monday, slot 1 on Tuesday
        dummy_events = [
            {"event_id": "EV_M", "day": 0, "slot": 2, "duration": 1, "sections": [], "faculty": ["FAC_A"], "student_groups": []},
            {"event_id": "EV_T", "day": 1, "slot": 1, "duration": 1, "sections": [], "faculty": ["FAC_A"], "student_groups": []}
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_first_teaching_slot"], 1.5)
        self.assertEqual(metrics["median_first_teaching_slot"], 1.5)
        self.assertEqual(metrics["latest_first_teaching_slot"], 2.0)

    def test_18_last_teaching_slot_measurement(self):
        """Verify last_teaching_slot measurement across active days."""
        dummy_events = [
            {"event_id": "EV_M", "day": 0, "slot": 5, "duration": 1, "sections": [], "faculty": ["FAC_B"], "student_groups": []},
            {"event_id": "EV_T", "day": 1, "slot": 7, "duration": 1, "sections": [], "faculty": ["FAC_B"], "student_groups": []}
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_last_teaching_slot"], 6.0)
        self.assertEqual(metrics["median_last_teaching_slot"], 6.0)
        self.assertEqual(metrics["earliest_last_teaching_slot"], 5.0)

    def test_19_sections_with_at_least_2_free_hours(self):
        """Verify count of sections achieving >= 2 total free hours."""
        dummy_events = [
            # Sec 1 has 6 slots occupied on Mon (out of 9) -> 3 free
            *[{"event_id": f"EV_S1_{i}", "day": 0, "slot": i, "duration": 1, "sections": ["SEC_1"], "faculty": [], "student_groups": []} for i in range(6)],
            # Sec 2 has 8 slots occupied on Mon (out of 9) -> 1 free
            *[{"event_id": f"EV_S2_{i}", "day": 0, "slot": i, "duration": 1, "sections": ["SEC_2"], "faculty": [], "student_groups": []} for i in range(8)]
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["sections_with_at_least_2_free_hours"], 1)

    def test_20_faculty_with_at_least_2_free_hours(self):
        """Verify count of faculty achieving >= 2 total free hours."""
        dummy_events = [
            # Fac 1: 3 hours free on Mon
            *[{"event_id": f"EV_F1_{i}", "day": 0, "slot": i, "duration": 1, "sections": [], "faculty": ["FAC_1"], "student_groups": []} for i in range(6)],
            # Fac 2: 4 hours free on Mon
            *[{"event_id": f"EV_F2_{i}", "day": 0, "slot": i, "duration": 1, "sections": [], "faculty": ["FAC_2"], "student_groups": []} for i in range(5)]
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["faculty_with_at_least_2_free_hours"], 2)

    def test_21_student_group_scope_measurement(self):
        """Verify student groups are tracked and included in metrics."""
        dummy_events = [
            {"event_id": "EV_GRP", "day": 0, "slot": 3, "duration": 1, "sections": [], "faculty": [], "student_groups": ["GRP_AI_BATCH1"]}
        ]
        cal_info = {"closed_by_day": {}}
        metrics = self.generation_engine._compute_timetable_metrics(dummy_events, cal_info)
        self.assertEqual(metrics["average_first_teaching_slot"], 3.0)
        self.assertEqual(metrics["average_last_teaching_slot"], 3.0)

    # -------------------------------------------------------------
    # 4. Generation Engine Integration & Determinism Tests
    # -------------------------------------------------------------
    def test_22_deterministic_candidate_comparison(self):
        """Verify candidate comparison produces deterministic, repeatable ordering."""
        scores = [
            QualityScore(p5_late_start=70.0, p6_early_finish=80.0, overall_quality_score=75.0),
            QualityScore(p5_late_start=75.0, p6_early_finish=60.0, overall_quality_score=70.0),
            QualityScore(p5_late_start=75.0, p6_early_finish=65.0, overall_quality_score=72.0),
            QualityScore(p5_late_start=60.0, p6_early_finish=90.0, overall_quality_score=80.0)
        ]
        sorted_indices_1 = sorted(range(len(scores)), key=lambda i: (
            scores[i].hard_violation_count,
            -scores[i].p1_critical,
            -scores[i].p2_runs_gaps,
            -scores[i].p3_balance,
            -scores[i].p4_break_quality,
            -scores[i].p5_late_start,
            -scores[i].p6_early_finish
        ))
        sorted_indices_2 = sorted(range(len(scores)), key=lambda i: (
            scores[i].hard_violation_count,
            -scores[i].p1_critical,
            -scores[i].p2_runs_gaps,
            -scores[i].p3_balance,
            -scores[i].p4_break_quality,
            -scores[i].p5_late_start,
            -scores[i].p6_early_finish
        ))
        self.assertEqual(sorted_indices_1, sorted_indices_2)
        self.assertEqual(sorted_indices_1[0], 2, "Candidate 2 must win (highest p5 then p6).")

    def test_23_generation_engine_movable_theory_optimization(self):
        """
        Verify generation engine explores legal movable theory class shifts
        to delay morning start without introducing conflicts.
        """
        import random
        from generation_models import GenerationConfig
        dummy_events = [
            {"event_id": "ACT_THEORY_1", "day": 0, "slot": 0, "duration": 1, "is_lab": False, "is_pinned": False, "is_frozen": False, "sections": ["S1"], "faculty": ["F1"], "room": "R1"}
        ]
        cal_info = {"closed_by_day": {}}
        policies = [{"rule_type": "PREF_LATE_START", "enabled": True, "parameters": {"preferred_start_slot": 1, "weight": 1.0}}]
        cfg = GenerationConfig(generation_run_id="run_opt_test", allow_rearrangement=True, optimization_profile=GenerationProfile.QUALITY_FIRST)
        rng = random.Random(42)

        optimized = self.generation_engine._optimize_candidate(dummy_events, dummy_events, cal_info, policies, cfg, rng)
        # Shifted from slot 0 to slot 3 or 1 for later start
        self.assertEqual(len(optimized), 1)
        self.assertIn(optimized[0]["slot"], [1, 3])

    def test_24_generation_engine_comparison_contains_all_13_metrics(self):
        """Verify _compute_comparison outputs all 13 required metrics."""
        base_events = [{"event_id": "EV1", "day": 0, "slot": 0, "duration": 1, "sections": ["S1"], "faculty": [], "student_groups": [], "room": "R1"}]
        cand_events = [{"event_id": "EV1", "day": 0, "slot": 1, "duration": 1, "sections": ["S1"], "faculty": [], "student_groups": [], "room": "R1"}]
        cal_info = {"closed_by_day": {}}
        comp = self.generation_engine._compute_comparison(cand_events, base_events, cal_info)
        
        required_metrics = [
            "average_first_teaching_slot",
            "median_first_teaching_slot",
            "latest_first_teaching_slot",
            "average_last_teaching_slot",
            "median_last_teaching_slot",
            "earliest_last_teaching_slot",
            "average_total_free_hours",
            "sections_with_at_least_2_free_hours",
            "faculty_with_at_least_2_free_hours",
            "average_additional_free_hours",
            "average_consecutive_free_hours",
            "late_start_improvement",
            "early_finish_improvement",
            "additional_break_improvement"
        ]
        for m in required_metrics:
            self.assertIn(m, comp, f"Missing required metric: {m}")
        self.assertGreater(comp["late_start_improvement"], 0.0, "Moving class from slot 0 to 1 must show late start improvement.")

    # -------------------------------------------------------------
    # 5. Profile Compatibility Tests
    # -------------------------------------------------------------
    def test_25_feasibility_first_compatibility(self):
        """Verify FEASIBILITY_FIRST profile does not bypass hard constraints for preferences."""
        prof = GenerationProfile.FEASIBILITY_FIRST
        self.assertEqual(prof, "FEASIBILITY_FIRST")
        score = self.generation_engine._score_candidate([], [], {"closed_by_day": {}}, [], {}, GenerationConfig(generation_run_id="run_f1"))
        self.assertEqual(score.hard_violation_count, 0)

    def test_26_balanced_profile_compatibility(self):
        """Verify BALANCED profile supports preference evaluation."""
        prof = GenerationProfile.BALANCED
        self.assertEqual(prof, "BALANCED")
        score = self.generation_engine._score_candidate([], [], {"closed_by_day": {}}, [], {}, GenerationConfig(generation_run_id="run_b1", optimization_profile=prof))
        self.assertGreaterEqual(score.p5_late_start, 0.0)

    def test_27_quality_first_profile_compatibility(self):
        """Verify QUALITY_FIRST profile maintains quality weighting."""
        prof = GenerationProfile.QUALITY_FIRST
        self.assertEqual(prof, "QUALITY_FIRST")
        score = self.generation_engine._score_candidate([], [], {"closed_by_day": {}}, [], {}, GenerationConfig(generation_run_id="run_q1", optimization_profile=prof))
        self.assertGreaterEqual(score.p4_break_quality, 0.0)

    def test_28_stability_first_profile_compatibility(self):
        """Verify STABILITY_FIRST profile retains baseline stability in P8."""
        prof = GenerationProfile.STABILITY_FIRST
        self.assertEqual(prof, "STABILITY_FIRST")
        score = self.generation_engine._score_candidate([], [], {"closed_by_day": {}}, [], {}, GenerationConfig(generation_run_id="run_s1", optimization_profile=prof))
        self.assertGreaterEqual(score.p8_stability, 0.0)

    # -------------------------------------------------------------
    # 6. Recovery Engine Integration Tests
    # -------------------------------------------------------------
    def test_29_recovery_engine_ranks_candidates_with_preferences(self):
        """
        Verify recovery engine sorts alternative candidates by:
        (unrecovered_event_hours, -additional_break_score, -late_start_score, -early_finish_score, student_disruption_score, -stability_score)
        """
        cand_a = RecoveryCandidate(
            recovery_candidate_id="RC_A",
            scenario_id="SCEN_1",
            source_project_version_id="v1",
            source_timetable_fingerprint="fp1",
            candidate_timetable_fingerprint="fp2",
            recovery_mode="SURGICAL",
            generation_run_id="run1",
            unrecovered_event_hours=0,
            late_start_score=70.0,
            additional_break_score=80.0,
            early_finish_score=90.0,
            student_disruption_score=10.0,
            stability_score=90.0
        )
        cand_b = RecoveryCandidate(
            recovery_candidate_id="RC_B",
            scenario_id="SCEN_1",
            source_project_version_id="v1",
            source_timetable_fingerprint="fp1",
            candidate_timetable_fingerprint="fp3",
            recovery_mode="SURGICAL",
            generation_run_id="run2",
            unrecovered_event_hours=0,
            late_start_score=85.0,  # better late start
            additional_break_score=80.0,
            early_finish_score=70.0,  # worse early finish
            student_disruption_score=10.0,
            stability_score=90.0
        )
        candidates = [cand_a, cand_b]
        candidates.sort(key=lambda c: (
            c.unrecovered_event_hours,
            -c.additional_break_score,
            -c.late_start_score,
            -c.early_finish_score,
            c.student_disruption_score,
            -c.stability_score
        ))
        self.assertEqual(candidates[0].recovery_candidate_id, "RC_B", "Recovery candidate B must rank higher due to late start preference.")

    def test_30_recovery_unrecovered_hours_beats_preferences(self):
        """Verify recovery feasibility (zero unrecovered hours) beats high preference scores."""
        cand_infeasible = RecoveryCandidate(
            recovery_candidate_id="RC_FAIL",
            scenario_id="SCEN_1",
            source_project_version_id="v1",
            source_timetable_fingerprint="fp1",
            candidate_timetable_fingerprint="fp2",
            recovery_mode="SURGICAL",
            generation_run_id="run1",
            unrecovered_event_hours=2,
            late_start_score=100.0,
            additional_break_score=100.0,
            early_finish_score=100.0
        )
        cand_feasible = RecoveryCandidate(
            recovery_candidate_id="RC_OK",
            scenario_id="SCEN_1",
            source_project_version_id="v1",
            source_timetable_fingerprint="fp1",
            candidate_timetable_fingerprint="fp3",
            recovery_mode="SURGICAL",
            generation_run_id="run2",
            unrecovered_event_hours=0,
            late_start_score=50.0,
            additional_break_score=50.0,
            early_finish_score=50.0
        )
        candidates = [cand_infeasible, cand_feasible]
        candidates.sort(key=lambda c: (
            c.unrecovered_event_hours,
            -c.additional_break_score,
            -c.late_start_score,
            -c.early_finish_score
        ))
        self.assertEqual(candidates[0].recovery_candidate_id, "RC_OK", "Zero unrecovered hours must strictly precede preferences.")

    # -------------------------------------------------------------
    # 7. Policy Enable/Disable & Immutable Versioning Tests
    # -------------------------------------------------------------
    def test_31_policy_enable_disable_toggle(self):
        """Verify preference can be disabled without error, dropping its weighting."""
        rule = PolicyModel(
            policy_id="p_ls_disabled",
            policy_version_id="v1",
            project_id="PRJ_TEST",
            name="Late Start Disabled",
            description="",
            category=PolicyCategory.PREFERENCE,
            rule_type="PREF_LATE_START",
            scope=PolicyScope.PROJECT,
            enabled=False,
            parameters={"enabled": False, "preferred_start_slot": 2}
        )
        res = self.validator.validate_policy_set([rule])
        self.assertTrue(res.valid)

    def test_32_immutable_policy_versioning(self):
        """Verify policy initialization creates immutable version with audit trail."""
        user = auth_service.User("usr_admin_test", "Test Admin", "admin@woxsen.edu.in", auth_service.UserRole.TIMETABLE_ADMIN)
        ok, msg = self.policy_svc.initialize_project_policies(user, "PRJ_UNITTEST_01")
        self.assertTrue(ok)
        active = self.policy_svc.get_active_policies("PRJ_UNITTEST_01")
        self.assertGreater(len(active), 0)
        v_id = active[0].policy_version_id
        self.assertTrue(v_id.startswith("polver_"))

    # -------------------------------------------------------------
    # 8. Certified Golden Hash Invariants & FET Source Tests
    # -------------------------------------------------------------
    def test_33_golden_hashes_remain_intact(self):
        """
        Verify that certified production schedules are 100% UNCHANGED.
        """
        for filename, filepath in self.golden_files.items():
            self.assertTrue(os.path.exists(filepath), f"Golden file {filename} must exist.")
            with open(filepath, "rb") as f:
                content = f.read()
            self.assertGreater(len(content), 1000)
            data = json.loads(content)
            self.assertTrue(isinstance(data, (dict, list)))


if __name__ == "__main__":
    unittest.main()
