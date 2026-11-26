"""
create_snapshot.py - Substage 6.1: Certified Schedule Snapshot Generator
Generates production_schedule.json and production_schedule_manifest.json with SHA256 integrity hash from stage5_3_corrected_optimized_schedule.json.
"""
import json
import hashlib
import os
import sys
from datetime import datetime
from parser import load_timetable_data

def generate_production_snapshot():
    print("=" * 80)
    print("STAGE 6.0 - SUBSTAGE 6.1: CERTIFIED SCHEDULE SNAPSHOT REBUILD FROM STAGE 5.3")
    print("=" * 80)

    # 1. Verify Stage 5.3 certification report
    with open('stage5_3_deep_certification_report.json', 'r', encoding='utf-8') as f:
        cert = json.load(f)
    assert cert.get('status') == 'STAGE_5_3_CERT_AUDIT_PASS', f"Invalid certification status: {cert.get('status')}"
    print("  -> Verified stage5_3_deep_certification_report.json: STAGE_5_3_CERT_AUDIT_PASS")

    # 2. Load authoritative data & candidate schedule
    data = load_timetable_data(".")
    master_events = data['events']
    days = data['days']
    slots = data['slots']

    with open('stage5_3_corrected_optimized_schedule.json', 'rb') as f:
        src_bytes = f.read()
    source_sha256 = hashlib.sha256(src_bytes).hexdigest()
    candidate_schedule = json.loads(src_bytes.decode('utf-8'))

    cand_map = {item['event_id']: (item['day'], item['slot']) for item in candidate_schedule}

    # 3. Build canonical production events
    production_events = []
    friday_post_lunch_hours = 0

    for e in master_events:
        eid = e['event_id']
        day, slot = cand_map[eid]
        
        # Check Friday post lunch
        if day == 4:
            for s in range(slot, slot + e['duration']):
                if s in [4, 5, 6, 7, 8]:
                    friday_post_lunch_hours += 1

        # Build complete production record
        rec = {
            'event_id': eid,
            'subject': e['subject'],
            'event_type': 'Lab' if e['is_lab'] else 'Theory',
            'is_lab': e['is_lab'],
            'duration': e['duration'],
            'day_idx': day,
            'day_name': days[day],
            'start_slot': slot,
            'end_slot': slot + e['duration'],
            'start_time': slots[slot].split(' - ')[0],
            'end_time': slots[slot + e['duration'] - 1].split(' - ')[1],
            'room': e['room'],
            'building': e['building'],
            'floor': e['floor'],
            'is_roomless': (e['room'] == 'NO_ROOM'),
            'is_pinned': e.get('is_pinned', False),
            'sections': sorted(list(e['sections'])),
            'faculty': sorted(list(e['faculty'])),
            'is_shared': len(e['sections']) > 1,
            'is_multi_faculty': len(e['faculty']) > 1,
            'baseline_day': e['baseline_day'],
            'baseline_slot': e['baseline_slot'],
            'is_displaced': (day != e['baseline_day'] or slot != e['baseline_slot'])
        }
        production_events.append(rec)

    # Sort deterministically by event_id
    production_events.sort(key=lambda x: x['event_id'])

    # 4. Assert snapshot requirements
    assert len(production_events) == 598, f"Event count mismatch: {len(production_events)}"
    total_sec_hours = sum(e['duration'] * len(e['sections']) for e in production_events)
    assert total_sec_hours == 748, f"Student hours mismatch: {total_sec_hours}"
    total_fac_hours = sum(e['duration'] * len(e['faculty']) for e in production_events)
    assert total_fac_hours == 981, f"Faculty hours mismatch: {total_fac_hours}"
    labs = [e for e in production_events if e['is_lab']]
    assert len(labs) == 75, f"Lab count mismatch: {len(labs)}"
    shared = [e for e in production_events if e['is_shared']]
    assert len(shared) == 38, f"Shared count mismatch: {len(shared)}"
    roomed = [e for e in production_events if not e['is_roomless']]
    assert len(roomed) == 595, f"Roomed count mismatch: {len(roomed)}"
    no_room = [e for e in production_events if e['is_roomless']]
    assert len(no_room) == 3, f"No-room count mismatch: {len(no_room)}"
    for nr in no_room:
        assert nr['day_idx'] == nr['baseline_day'] and nr['start_slot'] == nr['baseline_slot'], "Pinned event moved!"
    assert friday_post_lunch_hours == 0, f"Friday post-lunch hours: {friday_post_lunch_hours} != 0"

    # 5. Serialize production_schedule.json
    prod_json_bytes = json.dumps(production_events, indent=2, sort_keys=True).encode('utf-8')
    with open('production_schedule.json', 'wb') as f:
        f.write(prod_json_bytes)

    prod_hash = hashlib.sha256(prod_json_bytes).hexdigest()
    print(f"  -> Generated production_schedule.json (SHA-256: {prod_hash})")

    # 6. Build production_schedule_manifest.json with all required fields
    now_ts = datetime.utcnow().isoformat() + 'Z'
    manifest = {
        'manifest_version': '2.0.0',
        'stage': '6.0',
        'status': 'SUBSTAGE_6_1_PASS',
        'generation_timestamp': now_ts,
        'source_filename': 'stage5_3_corrected_optimized_schedule.json',
        'source_sha256': source_sha256,
        'production_filename': 'production_schedule.json',
        'production_sha256': prod_hash,
        'hash_algorithm': 'SHA-256',
        'stage_5_3_certification_report': 'stage5_3_deep_certification_report.json',
        'event_count': 598,
        'student_hours': 748,
        'faculty_hours': 981,
        'lab_count': 75,
        'shared_event_count': 38,
        'frozen_room_count': 595,
        'pinned_no_room_count': 3,
        'friday_post_lunch_event_hours': 0,
        'invariants': {
            'master_events': 598,
            'student_section_occupancy_hours': 748,
            'faculty_allocation_occupancy_hours': 981,
            'theory_events': 523,
            'lab_events': 75,
            'shared_multi_section_events': 38,
            'frozen_roomed_events': 595,
            'pinned_no_room_events': 3,
            'unchanged_placements': 399,
            'changed_placements': 199,
            'retention_percent': 66.7,
            'friday_post_lunch_event_hours': 0
        },
        'working_hours': '09:00 - 18:00',
        'time_slots': slots,
        'days': days,
        'source_files': [
            'B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Groups.html',
            'B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Rooms.html',
            'B.Tech  2023, 2024 , 2025 & 2026, BCA & M.Tech Timetable (7th September 2026 - 11th September 2026) Teachers.html'
        ]
    }

    with open('production_schedule_manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    print("  -> Generated production_schedule_manifest.json")
    print("SUBSTAGE 6.1: PASS\n")
    return prod_hash

if __name__ == "__main__":
    generate_production_snapshot()
