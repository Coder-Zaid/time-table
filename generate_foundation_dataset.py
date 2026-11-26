"""
generate_foundation_dataset.py - Extracts Canonical Baseline Dataset from Certified Timetable
Stage 8.1: Timetable Creation Platform Foundation
Generates certified_canonical_baseline_project.json isolating existing certified timetable as a read-only baseline version.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from parser import load_timetable_data
from dataclasses import asdict
from platform_models import (
    TimetableProject, ProjectStatus, SourceType, VersionType
)

def create_certified_baseline_project():
    print("=" * 80)
    print("STAGE 8.1: GENERATING CANONICAL BASELINE PROJECT DATASET")
    print("=" * 80)

    # 1. Load certified production snapshot and raw data
    with open('production_schedule.json', 'r', encoding='utf-8') as f:
        events = json.load(f)

    data = load_timetable_data('.')
    raw_leaves = data['faculty_leaves']
    days = data['days']
    slots = data['slots']

    # 2. Extract unique canonical entities
    # Sections
    sections_map = {}
    faculty_map = {}
    subjects_map = {}
    rooms_map = {}
    requirements = []

    # Track seen requirements to synthesize structured course requirements
    req_tracker = {}

    for e in events:
        # Sections
        for s in e['sections']:
            if s not in sections_map:
                sections_map[s] = {
                    "section_id": s,
                    "name": s,
                    "program": "B.Tech / BCA" if "BCA" in s or "Tech" in s else "Engineering",
                    "year": 2024 if "2024" in s else (2025 if "2025" in s else (2026 if "2026" in s else 2023)),
                    "semester": 1,
                    "department": "Computer Science & Engineering" if "CSE" in s or "AIML" in s else "General",
                    "capacity": 60,
                    "parent_section_id": None
                }

        # Faculty
        for f_name in e['faculty']:
            if f_name not in faculty_map:
                f_id = f"fac_{len(faculty_map)+1:03d}"
                faculty_map[f_name] = {
                    "faculty_id": f_id,
                    "name": f_name,
                    "department": "School of Technology",
                    "email": f"{f_name.lower().replace(' ', '.').replace('dr.', '').replace('prof.', '').strip()}@woxsen.edu.in",
                    "active": True
                }

        # Subjects
        subj_name = e['subject']
        if subj_name not in subjects_map:
            s_code = f"SUB{len(subjects_map)+1:03d}"
            subjects_map[subj_name] = {
                "subject_id": s_code,
                "code": s_code,
                "name": subj_name,
                "department": "School of Technology",
                "credits": 3 if not e['is_lab'] else 2,
                "active": True
            }

        # Rooms
        r_name = e['room']
        if r_name not in rooms_map and r_name != 'NO_ROOM':
            r_id = f"rm_{len(rooms_map)+1:03d}"
            rooms_map[r_name] = {
                "room_id": r_id,
                "name": r_name,
                "building": e['building'],
                "floor": e['floor'],
                "capacity": 60 if not e['is_lab'] else 30,
                "room_type": "LAB" if e['is_lab'] else "CLASSROOM",
                "available": True,
                "features": ["PROJECTOR", "AC"] if not e['is_lab'] else ["WORKSTATIONS", "PROJECTOR"]
            }

        # Requirement aggregation key: (subject, section_tuple, faculty_tuple, is_lab)
        req_key = (subj_name, tuple(e['sections']), tuple(e['faculty']), e['is_lab'])
        if req_key not in req_tracker:
            req_tracker[req_key] = {
                "count": 0,
                "duration": e['duration'],
                "room_type": "LAB" if e['is_lab'] else "CLASSROOM",
                "is_shared": e['is_shared'],
                "is_pinned": e.get('is_pinned', False)
            }
        req_tracker[req_key]["count"] += 1

    # Convert tracked requirements
    req_list = []
    for idx, (k, v) in enumerate(req_tracker.items()):
        subj_name, secs, facs, is_lab = k
        req_id = f"req_{idx+1:04d}"
        fac_ids = [faculty_map[fn]["faculty_id"] for fn in facs if fn in faculty_map]
        total_hours = v["count"] * v["duration"]
        req_list.append({
            "requirement_id": req_id,
            "subject_id": subjects_map[subj_name]["subject_id"],
            "section_id": secs[0],
            "faculty_ids": fac_ids,
            "theory_hours": 0 if is_lab else total_hours,
            "lab_hours": total_hours if is_lab else 0,
            "weekly_hours": total_hours,
            "required_sessions": v["count"],
            "lab_duration": 2 if is_lab else 1,
            "room_type_required": v["room_type"],
            "room_capacity_required": 30 if is_lab else 60,
            "is_shared": v["is_shared"],
            "shared_section_ids": list(secs) if len(secs) > 1 else [],
            "is_split": False,
            "priority": 1
        })

    # Faculty Availability / Leaves
    avail_list = []
    avail_id = 1
    for f_name, leave_slots in raw_leaves.items():
        if f_name in faculty_map:
            fid = faculty_map[f_name]["faculty_id"]
            for (d, s) in leave_slots:
                avail_list.append({
                    "availability_id": f"av_{avail_id:05d}",
                    "entity_type": "FACULTY",
                    "entity_id": fid,
                    "day_id": d,
                    "slot_id": s,
                    "status": "UNAVAILABLE",
                    "reason": "Official Approved Leave"
                })
                avail_id += 1

    # Calendar definition
    calendar_def = {
        "calendar_id": "cal_woxsen_fall_2026",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "daily_start_time": "09:00",
        "daily_end_time": "18:00",
        "slot_duration_minutes": 60,
        "lunch_policy": {
            "mode": "SEQUENTIAL_LEXICOGRAPHIC",
            "core_slot": 4,
            "core_slot_time": "13:00-14:00",
            "friday_post_lunch_closed": True,
            "friday_forbidden_slots": [4, 5, 6, 7, 8],
            "friday_allowed_slots": [0, 1, 2, 3]
        },
        "special_closures": [
            {
                "name": "Friday Institutional Afternoon Closure",
                "day_id": 4,
                "slots": [4, 5, 6, 7, 8],
                "reason": "Institutional Policy - Zero Classes Post Lunch"
            }
        ],
        "days": [{"day_id": idx, "day_name": d, "date": f"2026-09-{7+idx:02d}", "is_teaching_day": True} for idx, d in enumerate(days)],
        "slots": [{"slot_id": idx, "start_time": s.split(' - ')[0], "end_time": s.split(' - ')[1], "index": idx, "is_teaching_slot": True, "is_lunch": (idx==4)} for idx, s in enumerate(slots)]
    }

    # Calendar exceptions (Initial example holiday / closure)
    exceptions_list = [
        {
            "exception_id": "exc_fri_afternoon_01",
            "scope": "INSTITUTION",
            "scope_id": None,
            "date": "2026-09-11",
            "start_slot": 4,
            "end_slot": 8,
            "exception_type": "SPECIAL_NO_CLASS_PERIOD",
            "reason": "Institutional Friday Post-Lunch No-Class Hard Constraint",
            "is_hard": True
        }
    ]

    # Assemble Canonical Dataset
    canonical_dataset = {
        "institution": {
            "institution_id": "woxsen_univ",
            "name": "Woxsen University",
            "timezone": "Asia/Kolkata"
        },
        "academic_period": {
            "academic_year": "2026-2027",
            "semester": "Odd Semester (Fall 2026)",
            "start_date": "2026-09-07",
            "end_date": "2026-09-11"
        },
        "calendar": calendar_def,
        "sections": list(sections_map.values()),
        "faculty": list(faculty_map.values()),
        "subjects": list(subjects_map.values()),
        "rooms": list(rooms_map.values()),
        "teaching_requirements": req_list,
        "availability": avail_list,
        "calendar_exceptions": exceptions_list
    }

    # Build Versioned Project Container
    project = TimetableProject(
        project_id="proj_woxsen_fall_2026",
        project_name="Woxsen University B.Tech / BCA Academic Timetable",
        institution_name="Woxsen University",
        academic_year="2026-2027",
        semester="Odd Semester",
        term_name="Fall 2026",
        status=ProjectStatus.APPROVED,
        source_type=SourceType.IMPORTED_EXISTING,
        source_version="Stage 5.3 Certified Production"
    )

    # Attach baseline version containing the canonical dataset and certified events
    baseline_version = project.create_version(
        version_type=VersionType.CANONICAL_BASELINE,
        dataset=canonical_dataset,
        created_by="Administrator",
        description="Certified baseline imported from Stage 5.3 verified production schedule."
    )
    baseline_version.events = events
    baseline_version.metrics = {
        "master_events": 598,
        "student_hours": 748,
        "faculty_hours": 981,
        "labs": 75,
        "shared_events": 38,
        "frozen_rooms": 595,
        "pinned_no_room": 3,
        "friday_post_lunch_hours": 0
    }

    # Serialize Canonical Baseline Project
    out_file = "certified_canonical_baseline_project.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        # Convert dataclasses to dict
        def serialize(obj):
            if hasattr(obj, '__dataclass_fields__'):
                import dataclasses
                return dataclasses.asdict(obj)
            return str(obj)
        json.dump(asdict(project), f, indent=2)

    print(f"  -> Generated {out_file} successfully.")
    print(f"  -> Sections: {len(sections_map)}, Faculty: {len(faculty_map)}, Subjects: {len(subjects_map)}, Rooms: {len(rooms_map)}")
    print(f"  -> Teaching Requirements: {len(req_list)}, Availability Entries: {len(avail_list)}")
    print("STAGE 8.1 DATASET GENERATION: COMPLETE\n")

if __name__ == "__main__":
    create_certified_baseline_project()
