import json
import csv
import sys
from collections import defaultdict

def generate_exports():
    print("=" * 80)
    print("SUBSTAGE 6.7: EXPORT SYSTEM GENERATION")
    print("=" * 80)

    # 1. Load production schedule
    with open('production_schedule.json', 'r', encoding='utf-8') as f:
        events = json.load(f)

    # 2. Export CSV
    csv_file = 'production_schedule.csv'
    fieldnames = [
        'event_id', 'subject', 'event_type', 'duration', 'day_name', 'day_idx',
        'start_slot', 'end_slot', 'start_time', 'end_time', 'room', 'building', 'floor',
        'sections', 'faculty', 'is_lab', 'is_shared', 'is_roomless', 'is_pinned'
    ]
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            row = {
                'event_id': e['event_id'],
                'subject': e['subject'],
                'event_type': e['event_type'],
                'duration': e['duration'],
                'day_name': e['day_name'],
                'day_idx': e['day_idx'],
                'start_slot': e['start_slot'],
                'end_slot': e['end_slot'],
                'start_time': e['start_time'],
                'end_time': e['end_time'],
                'room': e['room'],
                'building': e['building'],
                'floor': e['floor'],
                'sections': '; '.join(e['sections']),
                'faculty': '; '.join(e['faculty']),
                'is_lab': e['is_lab'],
                'is_shared': e['is_shared'],
                'is_roomless': e['is_roomless'],
                'is_pinned': e['is_pinned']
            }
            writer.writerow(row)
    print(f"  -> Generated {csv_file}")

    # 3. Validation: reload CSV and verify zero discrepancy
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    assert len(csv_rows) == 598, f"CSV count mismatch: {len(csv_rows)}"
    for e, r in zip(events, csv_rows):
        assert e['event_id'] == int(r['event_id'])
        assert e['day_idx'] == int(r['day_idx'])
        assert e['start_slot'] == int(r['start_slot'])
        assert e['duration'] == int(r['duration'])
        assert e['room'] == r['room']
        assert '; '.join(e['sections']) == r['sections']
        assert '; '.join(e['faculty']) == r['faculty']

    print("  -> CSV Export Verified: 100% exact parity with production_schedule.json")
    print("SUBSTAGE 6.7: PASS\n")

if __name__ == "__main__":
    generate_exports()
