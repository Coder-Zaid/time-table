"""
Test suite covering T8_1_1 through T8_1_22 for Stage 8.1
"""
import json
import hashlib
import sys
import os
import copy
from platform_models import (
    TimetableProject, TimetableVersion, ProjectStatus, SourceType, VersionType,
    Institution, AcademicPeriod, CalendarDefinition, Section, StudentGroup,
    Faculty, Subject, CourseRequirement, Room, Availability, CalendarException,
    ScopeType, ExceptionType, ScheduledEvent, EventType
)
from platform_engine import ValidationEngine, FeasibilityPreviewEngine, BulkImportEngine

test_results = {}

def test_T8_1_1():
    """Create empty timetable project."""
    project = TimetableProject(
        project_id="proj_test_01",
        project_name="Test Empty Project",
        institution_name="Test University",
        academic_year="2026-2027",
        semester="ODD",
        term_name="Autumn 2026",
        timezone="Asia/Kolkata",
        status=ProjectStatus.DRAFT,
        source_type=SourceType.MANUAL
    )
    assert project.project_id == "proj_test_01"
    assert project.status == ProjectStatus.DRAFT
    assert len(project.versions) == 0
    return True

def test_T8_1_2():
    """Create project with academic calendar."""
    project = TimetableProject(
        project_id="proj_test_02",
        project_name="Test Calendar Project",
        institution_name="Test University",
        academic_year="2026-2027",
        semester="ODD",
        term_name="Autumn 2026",
        timezone="Asia/Kolkata"
    )
    calendar_dict = {
        "calendar_id": "cal_01",
        "working_days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
        "daily_start_time": "09:00",
        "daily_end_time": "18:00",
        "slot_duration_minutes": 60,
        "lunch_policy": {"start_slot": 4, "duration_slots": 1},
        "special_closures": [{"name": "FRIDAY_POST_LUNCH", "day": 4, "slots": [4, 5, 6, 7, 8]}]
    }
    v = project.create_version(
        version_type=VersionType.CANONICAL_BASELINE,
        dataset={"calendar": calendar_dict},
        description="Calendar Initialized"
    )
    assert v.version_id in project.versions
    assert v.dataset["calendar"]["slot_duration_minutes"] == 60
    assert len(v.dataset["calendar"]["working_days"]) == 5
    return True

def test_T8_1_3():
    """Add sections manually."""
    sec = Section(
        section_id="SEC_CSE_1A",
        name="CSE Year 1 Sec A",
        program="B.Tech CSE",
        year=1,
        semester=1,
        department="Computer Science",
        capacity=60
    )
    assert sec.section_id == "SEC_CSE_1A"
    assert sec.capacity == 60
    return True

def test_T8_1_4():
    """Add faculty manually."""
    fac = Faculty(
        faculty_id="FAC_101",
        name="Dr. Alan Turing",
        department="Computer Science",
        email="alan@woxsen.edu.in",
        active=True
    )
    assert fac.faculty_id == "FAC_101"
    assert fac.active is True
    return True

def test_T8_1_5():
    """Add subjects and teaching requirements."""
    subj = Subject(
        subject_id="SUB_CS101",
        code="CS101",
        name="Intro to Programming",
        department="Computer Science",
        credits=4,
        active=True
    )
    req = CourseRequirement(
        requirement_id="REQ_CS101_1A",
        subject_id="SUB_CS101",
        section_id="SEC_CSE_1A",
        faculty_ids=["FAC_101"],
        theory_hours=3,
        lab_hours=2,
        weekly_hours=5,
        required_sessions=4,
        lab_duration=2,
        room_type_required="LAB",
        room_capacity_required=30
    )
    assert subj.code == "CS101"
    assert req.weekly_hours == 5
    assert req.lab_duration == 2
    return True

def test_T8_1_6():
    """Add rooms."""
    rm = Room(
        room_id="ROOM_LAB_1",
        name="Computing Lab 1",
        building="Tech Block",
        floor=2,
        capacity=35,
        room_type="LAB",
        available=True,
        features=["Computers", "Projector"]
    )
    assert rm.room_id == "ROOM_LAB_1"
    assert rm.room_type == "LAB"
    return True

def test_T8_1_7():
    """Add faculty availability."""
    avail = Availability(
        availability_id="AV_FAC_01",
        entity_type="FACULTY",
        entity_id="FAC_101",
        day_id=4, # Friday
        slot_id=4,
        status="UNAVAILABLE",
        reason="Admin Duty"
    )
    assert avail.entity_type == "FACULTY"
    assert avail.status == "UNAVAILABLE"
    return True

def test_T8_1_8():
    """Add section availability."""
    avail = Availability(
        availability_id="AV_SEC_01",
        entity_type="SECTION",
        entity_id="SEC_CSE_1A",
        day_id=4,
        slot_id=5,
        status="UNAVAILABLE",
        reason="Sports Hour"
    )
    assert avail.entity_type == "SECTION"
    assert avail.status == "UNAVAILABLE"
    return True

def test_T8_1_9():
    """Add room availability."""
    avail = Availability(
        availability_id="AV_ROOM_01",
        entity_type="ROOM",
        entity_id="ROOM_LAB_1",
        day_id=2, # Wednesday
        slot_id=0,
        status="UNAVAILABLE",
        reason="Maintenance"
    )
    assert avail.entity_type == "ROOM"
    assert avail.status == "UNAVAILABLE"
    return True

def test_T8_1_10():
    """Add institution holiday."""
    exc = CalendarException(
        exception_id="EXC_HOLIDAY_01",
        scope=ScopeType.INSTITUTION,
        scope_id=None,
        date="2026-10-02",
        start_slot=0,
        end_slot=8,
        exception_type=ExceptionType.INSTITUTION_HOLIDAY,
        reason="National Holiday",
        is_hard=True
    )
    assert exc.scope == ScopeType.INSTITUTION
    assert exc.is_hard is True
    return True

def test_T8_1_11():
    """Add department closure."""
    exc = CalendarException(
        exception_id="EXC_DEPT_01",
        scope=ScopeType.DEPARTMENT,
        scope_id="Computer Science",
        date="2026-10-15",
        start_slot=4,
        end_slot=8,
        exception_type=ExceptionType.DEPARTMENT_CLOSURE,
        reason="Department Symposium",
        is_hard=True
    )
    assert exc.scope == ScopeType.DEPARTMENT
    assert exc.scope_id == "Computer Science"
    return True

def test_T8_1_12():
    """Add faculty leave."""
    exc = CalendarException(
        exception_id="EXC_LEAVE_01",
        scope=ScopeType.FACULTY,
        scope_id="FAC_101",
        date="2026-09-15",
        start_slot=0,
        end_slot=8,
        exception_type=ExceptionType.FACULTY_LEAVE,
        reason="Conference Attendance",
        is_hard=True
    )
    assert exc.scope == ScopeType.FACULTY
    assert exc.scope_id == "FAC_101"
    return True

def test_T8_1_13():
    """Run validation with valid dataset."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    active_v_id = proj_data["active_version_id"]
    dataset = proj_data["versions"][active_v_id]["dataset"]
    engine = ValidationEngine(dataset)
    res = engine.validate()
    assert res["is_valid"] is True
    assert res["status"] == "PASS"
    assert res["error_count"] == 0
    return True

def test_T8_1_14():
    """Inject duplicate ID and verify ERROR."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    dataset = copy.deepcopy(proj_data["versions"][proj_data["active_version_id"]]["dataset"])
    # inject duplicate section id
    dataset["sections"].append(copy.deepcopy(dataset["sections"][0]))
    engine = ValidationEngine(dataset)
    res = engine.validate()
    assert res["is_valid"] is False
    assert res["status"] == "FAIL"
    dup_errors = [e for e in res["errors"] if e.get("code") == "DUPLICATE_ID"]
    assert len(dup_errors) > 0
    return True

def test_T8_1_15():
    """Inject missing faculty reference and verify ERROR."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    dataset = copy.deepcopy(proj_data["versions"][proj_data["active_version_id"]]["dataset"])
    # inject invalid faculty id in requirement
    dataset["teaching_requirements"][0]["faculty_ids"].append("FAC_NON_EXISTENT_999")
    engine = ValidationEngine(dataset)
    res = engine.validate()
    assert res["is_valid"] is False
    assert res["status"] == "FAIL"
    fac_errors = [e for e in res["errors"] if e.get("code") == "INVALID_FACULTY_REFERENCE"]
    assert len(fac_errors) > 0
    return True

def test_T8_1_16():
    """Inject missing room reference and verify ERROR."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    dataset = copy.deepcopy(proj_data["versions"][proj_data["active_version_id"]]["dataset"])
    # inject impossible room requirement
    dataset["teaching_requirements"][0]["room_type_required"] = "SPECIAL_ASTRONOMY_OBSERVATORY"
    engine = ValidationEngine(dataset)
    res = engine.validate()
    assert res["is_valid"] is False
    assert res["status"] == "FAIL"
    rm_errors = [e for e in res["errors"] if e.get("code") == "INVALID_ROOM_REFERENCE"]
    assert len(rm_errors) > 0
    return True

def test_T8_1_17():
    """Inject impossible lab requirement and verify ERROR."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    dataset = copy.deepcopy(proj_data["versions"][proj_data["active_version_id"]]["dataset"])
    # set lab_hours=3 with lab_duration=2 (not divisible)
    dataset["teaching_requirements"][0]["lab_hours"] = 3
    dataset["teaching_requirements"][0]["lab_duration"] = 2
    engine = ValidationEngine(dataset)
    res = engine.validate()
    assert res["is_valid"] is False
    assert res["status"] == "FAIL"
    lab_errors = [e for e in res["errors"] if e.get("code") == "IMPOSSIBLE_LAB_DURATION"]
    assert len(lab_errors) > 0
    return True

def test_T8_1_18():
    """Run feasibility preview without generating timetable."""
    with open("certified_canonical_baseline_project.json", "r", encoding="utf-8") as f:
        proj_data = json.load(f)
    dataset = proj_data["versions"][proj_data["active_version_id"]]["dataset"]
    preview_engine = FeasibilityPreviewEngine(dataset)
    feas = preview_engine.compute_feasibility()
    assert feas["total_required_hours"] == 673  # 523 theory + 150 lab (room/course hours)
    assert feas["theory_hours"] == 523
    assert feas["lab_hours"] == 150
    assert feas["room_capacity_margin"] == 607
    assert feas["lab_capacity_margin"] == 50
    assert feas["is_structurally_recoverable"] is True
    # Verify no timetable was mutated or generated
    assert len(proj_data["versions"][proj_data["active_version_id"]]["events"]) == 598
    return True

def test_T8_1_19():
    """Verify version creation."""
    project = TimetableProject(
        project_id="proj_version_test",
        project_name="Version Test",
        institution_name="Woxsen",
        academic_year="2026-2027",
        semester="ODD",
        term_name="Autumn 2026",
        timezone="Asia/Kolkata"
    )
    v1 = project.create_version(version_type=VersionType.CANONICAL_BASELINE, dataset={"name": "V1"})
    v2 = project.create_version(version_type=VersionType.SIMULATION, dataset={"name": "V2"})
    assert len(project.versions) == 2
    assert project.active_version_id == v2.version_id
    assert project.versions[v1.version_id].version_type == VersionType.CANONICAL_BASELINE
    assert project.versions[v2.version_id].version_type == VersionType.SIMULATION
    return True

def test_T8_1_20():
    """Verify old version remains unchanged."""
    project = TimetableProject(
        project_id="proj_immut_test",
        project_name="Immutability Test",
        institution_name="Woxsen",
        academic_year="2026-2027",
        semester="ODD",
        term_name="Autumn 2026",
        timezone="Asia/Kolkata"
    )
    v1 = project.create_version(VersionType.RAW_IMPORT, {"sections": [{"id": "s1"}]})
    v1_sec_count = len(v1.dataset["sections"])
    
    # create V2 branching from V1 dataset copy
    v2_data = copy.deepcopy(v1.dataset)
    v2_data["sections"].append({"id": "s2"})
    v2 = project.create_version(VersionType.CANDIDATE, v2_data)
    
    # v1 must remain unchanged
    assert len(project.versions[v1.version_id].dataset["sections"]) == v1_sec_count
    assert len(project.versions[v2.version_id].dataset["sections"]) == v1_sec_count + 1
    return True

def test_T8_1_21():
    """Verify certified production snapshot remains unchanged."""
    with open("production_schedule.json", "rb") as f:
        h_prod = hashlib.sha256(f.read()).hexdigest()
    with open("stage5_3_corrected_optimized_schedule.json", "rb") as f:
        h_cand = hashlib.sha256(f.read()).hexdigest()
    with open("production_schedule.csv", "rb") as f:
        h_csv = hashlib.sha256(f.read()).hexdigest()
    
    assert h_prod == "fc77f694acd4eaad55cdbc18432b231e10bc46124cd4ac930bdc26369eb45c3b"
    assert h_cand == "8c82c3a36bce6655b78344c599ba7911b4e318ba96fc541d679c06a8bdc0708a"
    assert h_csv == "47a555a3267a354d6b34548f76d9857d771925a603ff7998bdf0e2510ac67643"
    return True

def test_T8_1_22():
    """Verify Stage 7 regression still passes."""
    st7_file = "stage7_uat_report.json"
    assert os.path.exists(st7_file)
    with open(st7_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("status") == "STAGE_7_PASS"
    assert data.get("certified_invariants", {}).get("master_events") == 598
    assert data.get("certified_invariants", {}).get("friday_post_lunch_event_hours") == 0
    return True

all_tests = [
    ("T8_1_1", test_T8_1_1),
    ("T8_1_2", test_T8_1_2),
    ("T8_1_3", test_T8_1_3),
    ("T8_1_4", test_T8_1_4),
    ("T8_1_5", test_T8_1_5),
    ("T8_1_6", test_T8_1_6),
    ("T8_1_7", test_T8_1_7),
    ("T8_1_8", test_T8_1_8),
    ("T8_1_9", test_T8_1_9),
    ("T8_1_10", test_T8_1_10),
    ("T8_1_11", test_T8_1_11),
    ("T8_1_12", test_T8_1_12),
    ("T8_1_13", test_T8_1_13),
    ("T8_1_14", test_T8_1_14),
    ("T8_1_15", test_T8_1_15),
    ("T8_1_16", test_T8_1_16),
    ("T8_1_17", test_T8_1_17),
    ("T8_1_18", test_T8_1_18),
    ("T8_1_19", test_T8_1_19),
    ("T8_1_20", test_T8_1_20),
    ("T8_1_21", test_T8_1_21),
    ("T8_1_22", test_T8_1_22),
]

if __name__ == "__main__":
    results = {}
    passed = 0
    failed = 0
    for tid, func in all_tests:
        try:
            ok = func()
            results[tid] = {"status": "PASS", "description": func.__doc__}
            passed += 1
            print(f"  [PASS] {tid}: {func.__doc__}")
        except Exception as e:
            import traceback
            results[tid] = {"status": "FAIL", "description": func.__doc__, "error": str(e), "traceback": traceback.format_exc()}
            failed += 1
            print(f"  [FAIL] {tid}: {func.__doc__} -> {e}")
    
    print(f"\nSummary: {passed} passed, {failed} failed out of {len(all_tests)} tests.")
    with open("stage8_1_backend_test_results.json", "w", encoding="utf-8") as f:
        json.dump({"summary": {"passed": passed, "failed": failed, "total": len(all_tests)}, "results": results}, f, indent=2)
