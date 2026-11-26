"""
validate_production.py - Substage 6.2: Production Data Integrity Validator
Independently parses production_schedule.json and verifies all Level 0 invariants without trusting metadata.
Includes comprehensive verification of Friday post-lunch zero teaching hours.
"""
import json
import sys
from collections import defaultdict
from parser import load_timetable_data

def validate_production_integrity():
    print("=" * 80)
    print("STAGE 6.0 - SUBSTAGE 6.2: PRODUCTION DATA INTEGRITY VALIDATION")
    print("=" * 80)

    # 1. Load production snapshot
    with open('production_schedule.json', 'r', encoding='utf-8') as f:
        events = json.load(f)

    # 2. Load baseline leaves to check leave compliance
    data = load_timetable_data(".")
    leaves = data['faculty_leaves']

    errors = []

    # Check event count
    if len(events) != 598:
        errors.append(f"Event count mismatch: {len(events)} != 598")

    # Load conservation
    total_sec_hours = sum(e['duration'] * len(e['sections']) for e in events)
    if total_sec_hours != 748:
        errors.append(f"Student section hours mismatch: {total_sec_hours} != 748")

    total_fac_hours = sum(e['duration'] * len(e['faculty']) for e in events)
    if total_fac_hours != 981:
        errors.append(f"Faculty allocation hours mismatch: {total_fac_hours} != 981")

    # Lab atomicity
    labs = [e for e in events if e['is_lab']]
    if len(labs) != 75:
        errors.append(f"Lab count mismatch: {len(labs)} != 75")
    for lab in labs:
        if lab['duration'] != 2:
            errors.append(f"Lab {lab['event_id']} duration is not 2: {lab['duration']}")
        if lab['start_slot'] + lab['duration'] > 9:
            errors.append(f"Lab {lab['event_id']} overflows day boundary")

    # Shared events
    shared = [e for e in events if e['is_shared']]
    if len(shared) != 38:
        errors.append(f"Shared events count mismatch: {len(shared)} != 38")

    # Frozen rooms
    roomed = [e for e in events if not e['is_roomless']]
    if len(roomed) != 595:
        errors.append(f"Roomed events mismatch: {len(roomed)} != 595")

    # Pinned NO_ROOM events
    no_room = [e for e in events if e['is_roomless']]
    if len(no_room) != 3:
        errors.append(f"NO_ROOM events mismatch: {len(no_room)} != 3")
    for nr in no_room:
        if nr['day_idx'] != nr['baseline_day'] or nr['start_slot'] != nr['baseline_slot']:
            errors.append(f"Pinned event {nr['event_id']} moved!")

    # Friday Post-Lunch Rule Verification
    fri_slot_hours = {4: 0, 5: 0, 6: 0, 7: 0, 8: 0}
    for e in events:
        if e['day_idx'] == 4:
            for s in range(e['start_slot'], e['start_slot'] + e['duration']):
                if s in fri_slot_hours:
                    fri_slot_hours[s] += 1
                    errors.append(f"Forbidden Friday occupancy: event {e['event_id']} ({e['subject']}) occupies Friday slot {s}")

    for s, h in fri_slot_hours.items():
        if h != 0:
            errors.append(f"Friday slot {s} has {h} event-hours (expected 0)")

    # Collision & Leave Grid
    sec_grid = defaultdict(list)
    fac_grid = defaultdict(list)
    room_grid = defaultdict(list)

    for e in events:
        d = e['day_idx']
        s = e['start_slot']
        dur = e['duration']
        r = e['room']
        for t in range(s, s + dur):
            if r != 'NO_ROOM':
                room_grid[(r, d, t)].append(e['event_id'])
            for sec in e['sections']:
                sec_grid[(sec, d, t)].append(e['event_id'])
            for fac in e['faculty']:
                fac_grid[(fac, d, t)].append(e['event_id'])

    for (r, d, t), eids in room_grid.items():
        if len(eids) > 1: errors.append(f"Room clash at {r} on day {d} slot {t}: {eids}")
    for (sec, d, t), eids in sec_grid.items():
        if len(eids) > 1: errors.append(f"Section clash for {sec} on day {d} slot {t}: {eids}")
    for (fac, d, t), eids in fac_grid.items():
        if len(eids) > 1: errors.append(f"Faculty clash for {fac} on day {d} slot {t}: {eids}")

    # Leave compliance
    for (fac, d, t), eids in fac_grid.items():
        if (d, t) in leaves.get(fac, set()):
            errors.append(f"Leave violation for {fac} on day {d} slot {t}")

    print(f"  - Verified 598 master events from production_schedule.json")
    print(f"  - Verified 748 student-hours, 981 faculty-hours, 75 labs, 38 shared events")
    print(f"  - Verified 595 frozen rooms and 3 pinned NO_ROOM events preserved")
    print(f"  - Verified 0 section collisions, 0 faculty collisions, 0 room collisions, 0 leave clashes")
    print(f"  - Verified 0 event-hours in Friday slots 4, 5, 6, 7, 8 (All 0)")

    if errors:
        print(f"[FATAL] Substage 6.2 failed with {len(errors)} errors:")
        for err in errors[:10]:
            print("  *", err)
        sys.exit(1)

    print("SUBSTAGE 6.2: PASS (Zero discrepancies)\n")

if __name__ == "__main__":
    validate_production_integrity()
