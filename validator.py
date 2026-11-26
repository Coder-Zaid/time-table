"""
validator.py - Comprehensive Level 0 Invariant & Quality Metric Suite
Fully reconciled to exact Stage 4.4 Definitions and Invariants
"""
from collections import defaultdict
import numpy as np

def validate_schedule(events, faculty_leaves, partial_x_hard=True):
    """
    Validates a schedule (list of events with 'day' and 'slot' assigned) against
    all Level 0 invariants and calculates all quality metrics under exact Stage 4.4 definitions.
    """
    errors = []
    
    # Invariant 1: Exactly 598 master events scheduled
    if len(events) != 598:
        errors.append(f"Event count mismatch: expected 598, got {len(events)}")

    # Invariant 2: Load conservation
    total_sec_hours = sum(e['duration'] * len(e['sections']) for e in events)
    if total_sec_hours != 748:
        errors.append(f"Student section hours mismatch: expected 748, got {total_sec_hours}")
        
    total_fac_hours = sum(e['duration'] * len(e['faculty']) for e in events)
    if total_fac_hours != 981:
        errors.append(f"Faculty allocation hours mismatch: expected 981, got {total_fac_hours}")

    # Track slot allocations
    room_slots = defaultdict(list)    # (room, day, slot) -> [event_id]
    sec_slots = defaultdict(list)     # (sec, day, slot) -> [event_id]
    fac_slots = defaultdict(list)     # (fac, day, slot) -> [event_id]

    for e in events:
        eid = e['event_id']
        d = e.get('day', e.get('baseline_day'))
        s = e.get('slot', e.get('baseline_slot'))
        dur = e['duration']
        room = e['room']
        
        # Check boundary
        if s + dur > 9:
            errors.append(f"Event {eid} overflows day boundary: day {d}, slot {s}, dur {dur}")
            
        # Pinned events check
        if e.get('is_pinned', False):
            if d != e['baseline_day'] or s != e['baseline_slot']:
                errors.append(f"Pinned event {eid} moved: baseline=({e['baseline_day']},{e['baseline_slot']}) vs ({d},{s})")
                
        # Fill time slots
        for t in range(s, s + dur):
            if room != 'NO_ROOM':
                room_slots[(room, d, t)].append(eid)
            for sec in e['sections']:
                sec_slots[(sec, d, t)].append(eid)
            for fac in e['faculty']:
                fac_slots[(fac, d, t)].append(eid)

    # Invariant 3: Zero Room Clashes
    for (r, d, t), eids in room_slots.items():
        if len(eids) > 1:
            errors.append(f"Room clash at {r} on day {d} slot {t}: events {eids}")

    # Invariant 4: Zero Section Clashes
    for (sec, d, t), eids in sec_slots.items():
        if len(eids) > 1:
            errors.append(f"Section clash for {sec} on day {d} slot {t}: events {eids}")

    # Invariant 5: Zero Faculty Clashes
    for (fac, d, t), eids in fac_slots.items():
        if len(eids) > 1:
            errors.append(f"Faculty clash for {fac} on day {d} slot {t}: events {eids}")

    # Invariant 6: Faculty Leave Exclusions
    if partial_x_hard:
        for (fac, d, t), eids in fac_slots.items():
            if (d, t) in faculty_leaves.get(fac, set()):
                errors.append(f"Faculty {fac} scheduled during leave (-x-) on day {d} slot {t}: events {eids}")

    # ----------------------------------------------------
    # Quality Metrics Calculation (Stage 4.4 Exact Formulation)
    # ----------------------------------------------------
    all_sections = sorted(list(set(sec for e in events for sec in e['sections'])))
    all_faculty = sorted(list(set(fac for e in events for fac in e['faculty'])))

    # Event ID to (building, floor)
    event_loc = {e['event_id']: (e['building'], e['floor']) for e in events}

    # 1. Zero-Buffer Inter-Building Moves
    sec_ev_dict = defaultdict(list)
    for e in events:
        for s in e['sections']:
            sec_ev_dict[s].append(e)

    fac_ev_dict = defaultdict(list)
    for e in events:
        for f in e['faculty']:
            fac_ev_dict[f].append(e)

    def compute_zero_buffer_moves(ev_dict):
        bldg_moves = 0
        floor_moves = 0
        for entity, ev_list in ev_dict.items():
            for d in range(5):
                day_evs = [e for e in ev_list if e.get('day', e.get('baseline_day')) == d]
                day_evs.sort(key=lambda x: x.get('slot', x.get('baseline_slot')))
                for i in range(len(day_evs)-1):
                    e1 = day_evs[i]
                    e2 = day_evs[i+1]
                    s1 = e1.get('slot', e1.get('baseline_slot'))
                    dur1 = e1['duration']
                    s2 = e2.get('slot', e2.get('baseline_slot'))
                    # Exact zero-buffer condition: e1 ends at e2 start
                    if s1 + dur1 == s2:
                        b1, f1 = event_loc[e1['event_id']]
                        b2, f2 = event_loc[e2['event_id']]
                        if b1 != 'UNKNOWN' and b2 != 'UNKNOWN':
                            if b1 != b2:
                                bldg_moves += 1
                            else:
                                if f1 != -1 and f2 != -1:
                                    floor_moves += abs(f1 - f2)
        return bldg_moves, floor_moves

    sec_bldg_trans, sec_floor_trans = compute_zero_buffer_moves(sec_ev_dict)
    fac_bldg_trans, fac_floor_trans = compute_zero_buffer_moves(fac_ev_dict)

    # 2. Lunch Metrics (Exact Boolean Formulation from Stage 4.4)
    # Valid 2-hour windows: (2,3), (3,4), (4,5)
    sec_slot4_occ = 0
    sec_valid_2h_windows = 0
    sec_lunch_window_viol = 0

    for sec in all_sections:
        for d in range(5):
            grid = [1 if (sec, d, t) in sec_slots else 0 for t in range(9)]
            if grid[4] == 1:
                sec_slot4_occ += 1
            w1 = (grid[2] == 0 and grid[3] == 0)
            w2 = (grid[3] == 0 and grid[4] == 0)
            w3 = (grid[4] == 0 and grid[5] == 0)
            num_valid = (1 if w1 else 0) + (1 if w2 else 0) + (1 if w3 else 0)
            sec_valid_2h_windows += num_valid
            if num_valid == 0:
                sec_lunch_window_viol += 1

    fac_slot4_occ = 0
    fac_valid_2h_windows = 0
    fac_lunch_window_viol = 0

    for fac in all_faculty:
        for d in range(5):
            grid = [1 if (fac, d, t) in fac_slots else 0 for t in range(9)]
            if grid[4] == 1:
                fac_slot4_occ += 1
            w1 = (grid[2] == 0 and grid[3] == 0)
            w2 = (grid[3] == 0 and grid[4] == 0)
            w3 = (grid[4] == 0 and grid[5] == 0)
            num_valid = (1 if w1 else 0) + (1 if w2 else 0) + (1 if w3 else 0)
            fac_valid_2h_windows += num_valid
            if num_valid == 0:
                fac_lunch_window_viol += 1

    # 3. Consecutive Runs (Both Families: Sliding Windows & Maximal Runs)
    sec_sliding_4 = 0
    sec_max_runs = defaultdict(int)
    sec_max_len = 0
    sec_isolated_gaps = 0
    sec_total_gaps = 0
    sec_daily_hours = defaultdict(lambda: [0]*5)

    for sec in all_sections:
        for d in range(5):
            grid = [1 if (sec, d, t) in sec_slots else 0 for t in range(9)]
            sec_daily_hours[sec][d] = sum(grid)
            
            # Sliding 4-hour windows
            for t in range(6):
                if all(grid[t+k] == 1 for k in range(4)):
                    sec_sliding_4 += 1

            # Maximal runs
            cur = 0
            for o in grid:
                if o == 1:
                    cur += 1
                else:
                    if cur > 0:
                        sec_max_runs[cur] += 1
                        if cur > sec_max_len: sec_max_len = cur
                    cur = 0
            if cur > 0:
                sec_max_runs[cur] += 1
                if cur > sec_max_len: sec_max_len = cur

            # Gaps
            if 1 in grid:
                first = grid.index(1)
                last = 8 - grid[::-1].index(1)
                inside = grid[first:last+1]
                gap_len = 0
                for v in inside:
                    if v == 0:
                        gap_len += 1
                        sec_total_gaps += 1
                    else:
                        if gap_len == 1:
                            sec_isolated_gaps += 1
                        gap_len = 0
                if gap_len == 1:
                    sec_isolated_gaps += 1

    fac_sliding_4 = 0
    fac_max_runs = defaultdict(int)
    fac_max_len = 0
    fac_isolated_gaps = 0
    fac_total_gaps = 0
    fac_daily_hours = defaultdict(lambda: [0]*5)

    for fac in all_faculty:
        for d in range(5):
            grid = [1 if (fac, d, t) in fac_slots else 0 for t in range(9)]
            fac_daily_hours[fac][d] = sum(grid)

            for t in range(6):
                if all(grid[t+k] == 1 for k in range(4)):
                    fac_sliding_4 += 1

            cur = 0
            for o in grid:
                if o == 1:
                    cur += 1
                else:
                    if cur > 0:
                        fac_max_runs[cur] += 1
                        if cur > fac_max_len: fac_max_len = cur
                    cur = 0
            if cur > 0:
                fac_max_runs[cur] += 1
                if cur > fac_max_len: fac_max_len = cur

            if 1 in grid:
                first = grid.index(1)
                last = 8 - grid[::-1].index(1)
                inside = grid[first:last+1]
                gap_len = 0
                for v in inside:
                    if v == 0:
                        gap_len += 1
                        fac_total_gaps += 1
                    else:
                        if gap_len == 1:
                            fac_isolated_gaps += 1
                        gap_len = 0
                if gap_len == 1:
                    fac_isolated_gaps += 1

    # 4. Stability Metrics
    events_same_day_and_slot = 0
    events_day_changed = 0
    events_slot_changed = 0
    total_slot_displacement = 0
    max_slot_displacement = 0

    for e in events:
        d = e.get('day', e.get('baseline_day'))
        s = e.get('slot', e.get('baseline_slot'))
        bd = e['baseline_day']
        bs = e['baseline_slot']
        
        if d == bd and s == bs:
            events_same_day_and_slot += 1
        if d != bd:
            events_day_changed += 1
        if s != bs:
            events_slot_changed += 1
            
        disp = abs(s - bs)
        total_slot_displacement += disp
        if disp > max_slot_displacement:
            max_slot_displacement = disp

    # Daily Balance Variance
    sec_variances = [float(np.var(hours)) for hours in sec_daily_hours.values() if sum(hours) > 0]
    fac_variances = [float(np.var(hours)) for hours in fac_daily_hours.values() if sum(hours) > 0]
    mean_sec_var = float(np.mean(sec_variances)) if sec_variances else 0.0
    mean_fac_var = float(np.mean(fac_variances)) if fac_variances else 0.0

    metrics = {
        # Travel (Stage 4.4 exact)
        'baseline_student_zero_buffer_building_moves': sec_bldg_trans,
        'baseline_faculty_zero_buffer_building_moves': fac_bldg_trans,
        'baseline_combined_zero_buffer_building_moves': sec_bldg_trans + fac_bldg_trans,
        'student_floor_transitions': sec_floor_trans,
        'faculty_floor_transitions': fac_floor_trans,
        # Lunch
        'student_slot_4_occupancy': sec_slot4_occ,
        'faculty_slot_4_occupancy': fac_slot4_occ,
        'student_valid_two_hour_lunch_window_count': sec_valid_2h_windows,
        'faculty_valid_two_hour_lunch_window_count': fac_valid_2h_windows,
        'student_lunch_window_violations': sec_lunch_window_viol,
        'faculty_lunch_window_violations': fac_lunch_window_viol,
        # Gaps
        'student_isolated_1h_gaps': sec_isolated_gaps,
        'student_total_gap_hours': sec_total_gaps,
        'faculty_isolated_1h_gaps': fac_isolated_gaps,
        'faculty_total_gap_hours': fac_total_gaps,
        # Consecutive Runs (Sliding & Maximal)
        'student_sliding_4_hour_windows': sec_sliding_4,
        'student_maximal_exact_4_hour_runs': sec_max_runs[4],
        'student_maximal_exact_5_hour_runs': sec_max_runs[5],
        'student_maximal_6_plus_runs': sum(v for k, v in sec_max_runs.items() if k >= 6),
        'student_maximum_consecutive_run_length': sec_max_len,
        'faculty_sliding_4_hour_windows': fac_sliding_4,
        'faculty_maximal_exact_4_hour_runs': fac_max_runs[4],
        'faculty_maximal_exact_5_hour_runs': fac_max_runs[5],
        'faculty_maximal_6_plus_runs': sum(v for k, v in fac_max_runs.items() if k >= 6),
        'faculty_maximum_consecutive_run_length': fac_max_len,
        # Workload balance
        'mean_student_daily_variance': round(mean_sec_var, 3),
        'mean_faculty_daily_variance': round(mean_fac_var, 3),
        # Stability
        'events_same_day_and_slot': events_same_day_and_slot,
        'events_day_changed': events_day_changed,
        'events_slot_changed': events_slot_changed,
        'total_slot_displacement': total_slot_displacement,
        'maximum_slot_displacement': max_slot_displacement
    }

    is_valid = (len(errors) == 0)
    return is_valid, errors, metrics

if __name__ == "__main__":
    from parser import load_timetable_data
    data = load_timetable_data(".")
    baseline_events = []
    for e in data['events']:
        ec = dict(e)
        ec['day'] = e['baseline_day']
        ec['slot'] = e['baseline_slot']
        baseline_events.append(ec)

    valid, errs, mets = validate_schedule(baseline_events, data['faculty_leaves'])
    print("Baseline Valid:", valid)
    print("Exact Travel Metrics:")
    print("  Student building moves:", mets['baseline_student_zero_buffer_building_moves'])
    print("  Faculty building moves:", mets['baseline_faculty_zero_buffer_building_moves'])
    print("  Combined building moves:", mets['baseline_combined_zero_buffer_building_moves'])
    print("Exact Lunch Metrics:")
    print("  Student slot 4:", mets['student_slot_4_occupancy'])
    print("  Faculty slot 4:", mets['faculty_slot_4_occupancy'])
    print("  Student 2h window violations:", mets['student_lunch_window_violations'])
    print("Exact Run Metrics:")
    print("  Student sliding 4h windows:", mets['student_sliding_4_hour_windows'])
    print("  Student maximal exact 4h runs:", mets['student_maximal_exact_4_hour_runs'])
    print("  Student maximal exact 5h runs:", mets['student_maximal_exact_5_hour_runs'])
