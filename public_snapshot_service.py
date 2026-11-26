"""
public_snapshot_service.py - Stage 12 Public Timetable Sanitization & Snapshot Creation
Creates an immutable public snapshot from an approved TimetableVersion.
Strictly sanitizes all internal administrative, review, audit, security, and policy details.
"""

import json
import os
import hashlib
from typing import Dict, List, Any, Tuple
from publication_models import (
    PublicEvent,
    PublicTimetableSnapshot,
    compute_hash
)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

TIME_SLOTS = [
    {"slot_index": 0, "start_time": "09:00 AM", "end_time": "10:00 AM", "label": "09:00 - 10:00 AM"},
    {"slot_index": 1, "start_time": "10:00 AM", "end_time": "11:00 AM", "label": "10:00 - 11:00 AM"},
    {"slot_index": 2, "start_time": "11:15 AM", "end_time": "12:15 PM", "label": "11:15 - 12:15 PM"},
    {"slot_index": 3, "start_time": "12:15 PM", "end_time": "01:15 PM", "label": "12:15 - 01:15 PM"},
    {"slot_index": 4, "start_time": "02:00 PM", "end_time": "03:00 PM", "label": "02:00 - 03:00 PM"},
    {"slot_index": 5, "start_time": "03:00 PM", "end_time": "04:00 PM", "label": "03:00 - 04:00 PM"},
    {"slot_index": 6, "start_time": "04:15 PM", "end_time": "05:15 PM", "label": "04:15 - 05:15 PM"},
]

def sanitize_event_to_public(raw_event: Dict[str, Any]) -> PublicEvent:
    """
    Sanitizes an internal timetable event into a safe PublicEvent.
    Strips internal database keys, teacher private contact info, policy weights, etc.
    """
    event_id = str(raw_event.get("event_id") or raw_event.get("activity_id") or raw_event.get("id") or "")
    subject = str(raw_event.get("subject") or raw_event.get("subject_name") or "Unassigned Subject")
    
    # Faculty extraction
    raw_fac = raw_event.get("faculty") or raw_event.get("teacher") or raw_event.get("faculty_name") or "Unassigned Faculty"
    multi_faculty = []
    if isinstance(raw_fac, list):
        multi_faculty = [str(f).strip() for f in raw_fac if str(f).strip()]
        faculty = " & ".join(multi_faculty) if multi_faculty else "Unassigned Faculty"
    elif isinstance(raw_fac, str):
        if "+" in raw_fac or "," in raw_fac or "&" in raw_fac:
            parts = [f.strip() for f in raw_fac.replace("+", ",").replace("&", ",").split(",") if f.strip()]
            if len(parts) > 1:
                multi_faculty = parts
        faculty = raw_fac
    else:
        faculty = str(raw_fac)

    # Section extraction
    raw_sec = raw_event.get("sections") or raw_event.get("section") or raw_event.get("students") or raw_event.get("section_name") or "Unassigned Section"
    shared_sections = []
    if isinstance(raw_sec, list):
        shared_sections = [str(s).strip() for s in raw_sec if str(s).strip()]
        section = " + ".join(shared_sections) if shared_sections else "Unassigned Section"
    elif isinstance(raw_sec, str):
        if "+" in raw_sec or "," in raw_sec:
            parts = [s.strip() for s in raw_sec.replace("+", ",").split(",") if s.strip()]
            if len(parts) > 1:
                shared_sections = parts
        section = raw_sec
    else:
        section = str(raw_sec)

    is_shared = bool(len(shared_sections) > 1 or raw_event.get("is_shared", False))

    room = str(raw_event.get("room") or raw_event.get("room_name") or "NO_ROOM")
    building = str(raw_event.get("building") or ("Campus Main" if room != "NO_ROOM" else "N/A"))
    floor = str(raw_event.get("floor") or ("Level 2" if "2" in room else "Level 1" if room != "NO_ROOM" else "N/A"))
    
    day = int(raw_event.get("day_idx") if "day_idx" in raw_event else raw_event.get("day", 0))
    day_name = DAY_NAMES[day] if 0 <= day < len(DAY_NAMES) else f"Day {day}"
    
    duration = int(raw_event.get("duration", 1))
    slot = int(raw_event.get("start_slot") if "start_slot" in raw_event else (raw_event.get("slot") or raw_event.get("time_slot") or 0))
    
    is_lab = bool(raw_event.get("is_lab") is True or duration == 2)
    event_type = "LAB" if is_lab else "THEORY"
    
    start_time = TIME_SLOTS[slot]["start_time"] if 0 <= slot < len(TIME_SLOTS) else f"{9+slot}:00 AM"
    end_slot = min(len(TIME_SLOTS) - 1, slot + duration - 1)
    end_time = TIME_SLOTS[end_slot]["end_time"] if 0 <= end_slot < len(TIME_SLOTS) else f"{9+slot+duration}:00 AM"
    
    return PublicEvent(
        event_id=event_id,
        subject_name=subject,
        faculty_name=faculty,
        section_name=section,
        room_name=room,
        building=building,
        floor=floor,
        day=day,
        day_name=day_name,
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration,
        event_type=event_type,
        is_lab=is_lab,
        is_shared=is_shared,
        shared_sections=shared_sections,
        multi_faculty=multi_faculty
    )

def build_public_timetable_snapshot(
    publication_id: str,
    public_slug: str,
    title: str,
    institution_name: str,
    academic_period: str,
    effective_from: str,
    effective_to: str,
    published_at: str,
    raw_events: List[Dict[str, Any]]
) -> PublicTimetableSnapshot:
    """
    Builds a complete, deterministic, sanitized public snapshot from raw timetable events.
    """
    public_events: List[PublicEvent] = []
    sections_set = set()
    faculties_set = set()
    rooms_set = set()
    subjects_set = set()

    total_student_hours = 0
    total_faculty_hours = 0
    total_labs = 0
    total_shared_events = 0
    total_no_room = 0

    for raw in raw_events:
        pe = sanitize_event_to_public(raw)
        public_events.append(pe)
        
        # Entity collections
        sections_set.add(pe.section_name)
        if pe.shared_sections:
            for s in pe.shared_sections:
                sections_set.add(s)
        
        faculties_set.add(pe.faculty_name)
        if pe.multi_faculty:
            for f in pe.multi_faculty:
                faculties_set.add(f)
                
        rooms_set.add(pe.room_name)
        subjects_set.add(pe.subject_name)

        # Hours & counts
        dur = pe.duration_hours
        # Student hours count per section
        sec_count = len(pe.shared_sections) if pe.is_shared and pe.shared_sections else 1
        fac_count = len(pe.multi_faculty) if pe.multi_faculty else 1
        
        total_student_hours += (dur * sec_count)
        total_faculty_hours += (dur * fac_count)
        
        if pe.is_lab:
            total_labs += 1
        if pe.is_shared:
            total_shared_events += 1
        if pe.room_name == "NO_ROOM":
            total_no_room += 1

    # Sort events deterministically
    sorted_events = sorted(
        [pe.to_dict() for pe in public_events],
        key=lambda x: (x["day"], x["start_time"], x["section_name"], x["room_name"])
    )

    days_catalog = [{"day": i, "name": name} for i, name in enumerate(DAY_NAMES)]

    snapshot_data = {
        "publication_id": publication_id,
        "public_slug": public_slug,
        "title": title,
        "institution_name": institution_name,
        "academic_period": academic_period,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "published_at": published_at,
        "total_events": len(sorted_events),
        "total_student_hours": total_student_hours,
        "total_faculty_hours": total_faculty_hours,
        "total_labs": total_labs,
        "total_shared_events": total_shared_events,
        "total_no_room_events": total_no_room,
        "sections": sorted(list(sections_set)),
        "faculties": sorted(list(faculties_set)),
        "rooms": sorted(list(rooms_set)),
        "subjects": sorted(list(subjects_set)),
        "days": days_catalog,
        "time_slots": TIME_SLOTS,
        "events": sorted_events
    }

    fingerprint = compute_hash(snapshot_data)
    snapshot_data["fingerprint"] = fingerprint

    return PublicTimetableSnapshot.from_dict(snapshot_data)

def write_publication_storage(
    base_storage_dir: str,
    publication_id: str,
    publication_record_dict: Dict[str, Any],
    snapshot: PublicTimetableSnapshot
) -> Tuple[str, str, str, str]:
    """
    Writes isolated immutable publication artifacts into:
      projects/published/<publication_id>/publication.json
      projects/published/<publication_id>/snapshot.json
      projects/published/<publication_id>/snapshot.sha256
      projects/published/<publication_id>/public_index.json
    """
    # Security: prevent path traversal in publication_id
    if ".." in publication_id or publication_id.startswith("/") or publication_id.startswith("\\"):
        raise ValueError("Invalid publication_id: path traversal detected")
    safe_pub_id = os.path.basename(publication_id).replace("..", "").replace("/", "").replace("\\", "")
    if not safe_pub_id:
        raise ValueError("Invalid publication_id: path traversal detected")

    pub_dir = os.path.join(base_storage_dir, "projects", "published", safe_pub_id)
    os.makedirs(pub_dir, exist_ok=True)

    pub_json_path = os.path.join(pub_dir, "publication.json")
    snap_json_path = os.path.join(pub_dir, "snapshot.json")
    snap_sha_path = os.path.join(pub_dir, "snapshot.sha256")
    pub_index_path = os.path.join(pub_dir, "public_index.json")

    # Write publication.json
    with open(pub_json_path, "w", encoding="utf-8") as f:
        json.dump(publication_record_dict, f, indent=2)

    # Write snapshot.json
    snap_dict = snapshot.to_dict()
    snap_bytes = json.dumps(snap_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    with open(snap_json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(snap_dict, indent=2))

    # Write snapshot.sha256
    snap_sha = hashlib.sha256(snap_bytes).hexdigest()
    with open(snap_sha_path, "w", encoding="utf-8") as f:
        f.write(snap_sha)

    # Precompute public_index.json for ultra-fast lookup by section, faculty, room, day
    section_index = {}
    faculty_index = {}
    room_index = {}
    day_index = {i: [] for i in range(5)}

    for ev in snapshot.events:
        eid = ev["event_id"]
        # Section index
        sec = ev["section_name"]
        section_index.setdefault(sec, []).append(eid)
        for s in ev.get("shared_sections", []):
            section_index.setdefault(s, []).append(eid)

        # Faculty index
        fac = ev["faculty_name"]
        faculty_index.setdefault(fac, []).append(eid)
        for f in ev.get("multi_faculty", []):
            faculty_index.setdefault(f, []).append(eid)

        # Room index
        rm = ev["room_name"]
        room_index.setdefault(rm, []).append(eid)

        # Day index
        d = ev["day"]
        if d in day_index:
            day_index[d].append(eid)

    public_index = {
        "publication_id": publication_id,
        "public_slug": snapshot.public_slug,
        "total_events": len(snapshot.events),
        "section_events": section_index,
        "faculty_events": faculty_index,
        "room_events": room_index,
        "day_events": day_index
    }

    with open(pub_index_path, "w", encoding="utf-8") as f:
        json.dump(public_index, f, indent=2)

    return pub_json_path, snap_json_path, snap_sha_path, pub_index_path
