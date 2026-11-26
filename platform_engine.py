"""
platform_engine.py - Validation Engine, Calendar Exception Engine, Feasibility Preview & Bulk Import
Stage 8.1: Timetable Creation Platform Foundation
"""
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from platform_models import Severity

class ValidationEngine:
    """
    Independent validation engine verifying structural dataset correctness.
    Classifies issues into ERROR (blocks generation), WARNING, and INFO.
    """
    def __init__(self, dataset: Dict[str, Any]):
        self.dataset = dataset
        self.sections = {s['section_id']: s for s in dataset.get('sections', []) if isinstance(s, dict) and s.get('section_id')}
        self.faculty = {f['faculty_id']: f for f in dataset.get('faculty', []) if isinstance(f, dict) and f.get('faculty_id')}
        self.subjects = {s['subject_id']: s for s in dataset.get('subjects', []) if isinstance(s, dict) and s.get('subject_id')}
        self.rooms = {r['room_id']: r for r in dataset.get('rooms', []) if isinstance(r, dict) and r.get('room_id')}
        self.requirements = dataset.get('teaching_requirements', [])
        self.calendar = dataset.get('calendar', {})
        self.exceptions = dataset.get('calendar_exceptions', [])
        self.availability = dataset.get('availability', [])

    def validate(self) -> Dict[str, Any]:
        errors = []
        warnings = []
        info = []

        # 1. Duplicate ID Checks
        sec_ids = set()
        for s in self.dataset.get('sections', []):
            sid = s.get('section_id')
            if not sid:
                errors.append({"code": "MISSING_REQUIRED_FIELD", "entity": "section", "message": "Section missing section_id"})
            elif sid in sec_ids:
                errors.append({"code": "DUPLICATE_ID", "entity": "section", "id": sid, "message": f"Duplicate section ID: {sid}"})
            sec_ids.add(sid)

        fac_ids = set()
        for f in self.dataset.get('faculty', []):
            fid = f.get('faculty_id')
            if not fid:
                errors.append({"code": "MISSING_REQUIRED_FIELD", "entity": "faculty", "message": "Faculty missing faculty_id"})
            elif fid in fac_ids:
                errors.append({"code": "DUPLICATE_ID", "entity": "faculty", "id": fid, "message": f"Duplicate faculty ID: {fid}"})
            fac_ids.add(fid)

        subj_ids = set()
        for s in self.dataset.get('subjects', []):
            s_id = s.get('subject_id')
            if not s_id:
                errors.append({"code": "MISSING_REQUIRED_FIELD", "entity": "subject", "message": "Subject missing subject_id"})
            elif s_id in subj_ids:
                errors.append({"code": "DUPLICATE_ID", "entity": "subject", "id": s_id, "message": f"Duplicate subject ID: {s_id}"})
            subj_ids.add(s_id)

        rm_ids = set()
        for r in self.dataset.get('rooms', []):
            rid = r.get('room_id')
            if not rid:
                errors.append({"code": "MISSING_REQUIRED_FIELD", "entity": "room", "message": "Room missing room_id"})
            elif rid in rm_ids:
                errors.append({"code": "DUPLICATE_ID", "entity": "room", "id": rid, "message": f"Duplicate room ID: {rid}"})
            rm_ids.add(rid)

        # 2. Reference Integrity in Teaching Requirements
        req_ids = set()
        for req in self.requirements:
            rid = req.get('requirement_id')
            if not rid:
                errors.append({"code": "MISSING_REQUIRED_FIELD", "entity": "course_requirement", "message": "Requirement missing requirement_id"})
            elif rid in req_ids:
                errors.append({"code": "DUPLICATE_ID", "entity": "course_requirement", "id": rid, "message": f"Duplicate requirement ID: {rid}"})
            req_ids.add(rid)

            # Check section ref
            sec_ref = req.get('section_id')
            if sec_ref not in self.sections:
                errors.append({"code": "INVALID_SECTION_REFERENCE", "requirement_id": rid, "target": sec_ref, "message": f"Requirement {rid} references non-existent section: {sec_ref}"})

            # Check subject ref
            sub_ref = req.get('subject_id')
            if sub_ref not in self.subjects:
                errors.append({"code": "INVALID_SUBJECT_REFERENCE", "requirement_id": rid, "target": sub_ref, "message": f"Requirement {rid} references non-existent subject: {sub_ref}"})

            # Check faculty refs
            fac_refs = req.get('faculty_ids', [])
            if not fac_refs:
                warnings.append({"code": "UNASSIGNED_FACULTY", "requirement_id": rid, "message": f"Requirement {rid} has no assigned faculty"})
            else:
                for f_ref in fac_refs:
                    if f_ref not in self.faculty:
                        errors.append({"code": "INVALID_FACULTY_REFERENCE", "requirement_id": rid, "target": f_ref, "message": f"Requirement {rid} references non-existent faculty: {f_ref}"})

            # Lab duration check
            lab_hrs = req.get('lab_hours', 0)
            lab_dur = req.get('lab_duration', 2)
            if lab_hrs > 0:
                if lab_dur <= 0 or lab_hrs % lab_dur != 0:
                    errors.append({"code": "IMPOSSIBLE_LAB_DURATION", "requirement_id": rid, "message": f"Requirement {rid} has lab_hours={lab_hrs} not cleanly divisible by lab_duration={lab_dur}"})

            # Room type / capacity check
            req_rm_type = req.get('room_type_required')
            req_cap = req.get('room_capacity_required', 0)
            matching_rooms = [r for r in self.rooms.values() if r.get('room_type') == req_rm_type and r.get('capacity', 0) >= req_cap]
            if req_rm_type and not matching_rooms and req_rm_type != 'NO_ROOM':
                errors.append({"code": "INVALID_ROOM_REFERENCE", "requirement_id": rid, "message": f"Requirement {rid} requires room_type={req_rm_type} (capacity>={req_cap}) but no suitable rooms exist"})

        # 3. Calendar & Working Slot Definitions
        w_days = self.calendar.get('working_days', [])
        if not w_days:
            errors.append({"code": "INVALID_CALENDAR", "message": "Academic calendar has no working days defined"})
        slot_dur = self.calendar.get('slot_duration_minutes', 60)
        if slot_dur <= 0:
            errors.append({"code": "INVALID_SLOT_DEFINITION", "message": f"Invalid slot duration: {slot_dur}"})

        # 4. Summary & Status
        is_valid = (len(errors) == 0)
        return {
            "is_valid": is_valid,
            "status": "PASS" if is_valid else "FAIL",
            "error_count": len(errors),
            "warning_count": len(warnings),
            "info_count": len(info),
            "errors": errors,
            "warnings": warnings,
            "info": info
        }

class FeasibilityPreviewEngine:
    """
    Computes capacity margins and potential structural bottlenecks without generating timetable.
    """
    def __init__(self, dataset: Dict[str, Any]):
        self.dataset = dataset
        self.requirements = dataset.get('teaching_requirements', [])
        self.sections = dataset.get('sections', [])
        self.faculty = dataset.get('faculty', [])
        self.rooms = dataset.get('rooms', [])
        self.calendar = dataset.get('calendar', {})
        self.exceptions = dataset.get('calendar_exceptions', [])

    def compute_feasibility(self) -> Dict[str, Any]:
        working_days_count = len(self.calendar.get('working_days', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']))
        # Default 9 slots per day = 45 weekly slots (minus Friday lunch closure = 40)
        friday_closure = self.calendar.get('lunch_policy', {}).get('friday_post_lunch_closed', True)
        slots_per_day = 9
        weekly_teaching_slots = (working_days_count * slots_per_day) - (5 if friday_closure else 0)

        # 1. Total Required Hours
        total_theory_hours = sum(r.get('theory_hours', 0) for r in self.requirements)
        total_lab_hours = sum(r.get('lab_hours', 0) for r in self.requirements)
        total_required_hours = total_theory_hours + total_lab_hours

        # 2. Available Capacity
        # Section capacity
        sec_capacity = len(self.sections) * weekly_teaching_slots
        # Faculty capacity (assuming max ~24-30 hrs or 40 slots)
        fac_capacity = len(self.faculty) * weekly_teaching_slots
        # Room capacity
        room_capacity = len(self.rooms) * weekly_teaching_slots
        lab_rooms = [r for r in self.rooms if r.get('room_type') == 'LAB']
        lab_room_capacity = len(lab_rooms) * weekly_teaching_slots

        # 3. Holiday and Exception Impact
        holiday_impact_hours = 0
        for exc in self.exceptions:
            if exc.get('is_hard', True):
                duration = exc.get('end_slot', 8) - exc.get('start_slot', 0) + 1
                holiday_impact_hours += duration

        # 4. Bottleneck Detection
        unresolved_requirements = []
        for r in self.requirements:
            sec_id = r.get('section_id')
            sec_reqs = sum(req.get('weekly_hours', 0) for req in self.requirements if req.get('section_id') == sec_id)
            if sec_reqs > weekly_teaching_slots:
                unresolved_requirements.append({
                    "requirement_id": r.get('requirement_id'),
                    "section_id": sec_id,
                    "reason": f"Section {sec_id} weekly hours ({sec_reqs}) exceed weekly teaching slots ({weekly_teaching_slots})"
                })

        lab_capacity_margin = lab_room_capacity - total_lab_hours
        room_capacity_margin = room_capacity - total_required_hours

        is_recoverable = (room_capacity_margin >= 0 and lab_capacity_margin >= 0 and len(unresolved_requirements) == 0)

        if is_recoverable:
            feasibility_message = "All required teaching hours appear structurally recoverable within current calendar capacity."
        elif lab_capacity_margin < 0:
            feasibility_message = f"Insufficient lab capacity detected: deficit of {abs(lab_capacity_margin)} lab hours."
        else:
            feasibility_message = "Potential capacity bottleneck detected. Review unresolved requirements."

        return {
            "total_required_hours": total_required_hours,
            "theory_hours": total_theory_hours,
            "lab_hours": total_lab_hours,
            "weekly_teaching_slots_per_entity": weekly_teaching_slots,
            "available_section_capacity": sec_capacity,
            "available_faculty_capacity": fac_capacity,
            "available_room_capacity": room_capacity,
            "lab_room_capacity": lab_room_capacity,
            "room_capacity_margin": room_capacity_margin,
            "lab_capacity_margin": lab_capacity_margin,
            "holiday_impact_hours": holiday_impact_hours,
            "unresolved_requirements_count": len(unresolved_requirements),
            "unresolved_requirements": unresolved_requirements,
            "is_structurally_recoverable": is_recoverable,
            "feasibility_message": feasibility_message
        }

class BulkImportEngine:
    """
    Parses structured tabular data (CSV rows/Dicts) with column mapping and schema validation.
    """
    @staticmethod
    def import_entities(entity_type: str, rows: List[Dict[str, Any]], column_mapping: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        valid_records = []
        errors = []
        seen_ids = set()

        id_key = f"{entity_type}_id" if entity_type != "teaching_requirements" else "requirement_id"
        if entity_type == "rooms": id_key = "room_id"
        elif entity_type == "subjects": id_key = "subject_id"
        elif entity_type == "sections": id_key = "section_id"
        elif entity_type == "faculty": id_key = "faculty_id"

        for idx, row in enumerate(rows):
            mapped_row = {}
            for k, v in row.items():
                target_key = column_mapping.get(k, k) if column_mapping else k
                mapped_row[target_key] = v

            entity_id = mapped_row.get(id_key)
            if not entity_id:
                errors.append({"row_index": idx, "code": "MISSING_ID", "message": f"Row {idx+1} is missing mandatory field '{id_key}'"})
                continue
            if entity_id in seen_ids:
                errors.append({"row_index": idx, "code": "DUPLICATE_ID", "message": f"Row {idx+1} has duplicate ID '{entity_id}'"})
                continue

            seen_ids.add(entity_id)
            valid_records.append(mapped_row)

        return valid_records, errors
