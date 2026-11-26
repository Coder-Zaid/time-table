"""
solver.py - MILP Timetable Lexicographic Optimization Engine
Using SciPy MILP (HiGHS solver) with Strict Lexicographic Bound Freezing
"""
import numpy as np
from scipy.optimize import milp, LinearConstraint
from scipy.sparse import dok_matrix, csc_matrix, vstack
from collections import defaultdict
import time

def build_slot_domains(events, faculty_leaves, partial_x_hard=True):
    domains = {}
    for e in events:
        eid = e['event_id']
        dur = e['duration']
        if e.get('is_pinned', False):
            domains[eid] = [(e['baseline_day'], e['baseline_slot'])]
            continue
            
        valid = []
        max_slot = 9 - dur
        fac_set = set(e['faculty'])
        
        for d in range(5):
            for t in range(max_slot + 1):
                clash = False
                if partial_x_hard:
                    for f in fac_set:
                        for dt in range(dur):
                            if (d, t + dt) in faculty_leaves.get(f, set()):
                                clash = True
                                break
                        if clash:
                            break
                if not clash:
                    valid.append((d, t))
        domains[eid] = valid
    return domains

class TimetableMILP:
    def __init__(self, events, faculty_leaves, partial_x_hard=True):
        self.events = events
        self.faculty_leaves = faculty_leaves
        self.partial_x_hard = partial_x_hard
        self.domains = build_slot_domains(events, faculty_leaves, partial_x_hard)
        
        # Binary variables: x_{e, d, t}
        self.var_map = {}
        self.rev_var_map = {}
        var_idx = 0
        for e in events:
            eid = e['event_id']
            for (d, t) in self.domains[eid]:
                self.var_map[(eid, d, t)] = var_idx
                self.rev_var_map[var_idx] = (eid, d, t)
                var_idx += 1
                
        self.num_x_vars = var_idx
        print(f"[MILP Model] Total binary placement variables: {self.num_x_vars}")

    def build_core_constraints(self):
        row_list = []
        lhs_list = []
        rhs_list = []

        # 1. Exact event placement: sum_{d,t} x_{e,d,t} = 1
        for e in self.events:
            eid = e['event_id']
            row = {}
            for (d, t) in self.domains[eid]:
                row[self.var_map[(eid, d, t)]] = 1.0
            row_list.append(row)
            lhs_list.append(1.0)
            rhs_list.append(1.0)

        # 2. Room capacity: sum x <= 1
        room_events = defaultdict(list)
        for e in self.events:
            if e['room'] != 'NO_ROOM':
                room_events[e['room']].append(e)

        for room, ev_list in room_events.items():
            for d in range(5):
                for t in range(9):
                    row = {}
                    for e in ev_list:
                        eid = e['event_id']
                        dur = e['duration']
                        for start_t in range(max(0, t - dur + 1), t + 1):
                            if (eid, d, start_t) in self.var_map:
                                row[self.var_map[(eid, d, start_t)]] = 1.0
                    if len(row) > 1:
                        row_list.append(row)
                        lhs_list.append(0.0)
                        rhs_list.append(1.0)

        # 3. Section non-overlap: sum x <= 1
        sec_events = defaultdict(list)
        for e in self.events:
            for s in e['sections']:
                sec_events[s].append(e)

        for sec, ev_list in sec_events.items():
            for d in range(5):
                for t in range(9):
                    row = {}
                    for e in ev_list:
                        eid = e['event_id']
                        dur = e['duration']
                        for start_t in range(max(0, t - dur + 1), t + 1):
                            if (eid, d, start_t) in self.var_map:
                                row[self.var_map[(eid, d, start_t)]] = 1.0
                    if len(row) > 1:
                        row_list.append(row)
                        lhs_list.append(0.0)
                        rhs_list.append(1.0)

        # 4. Faculty non-overlap: sum x <= 1
        fac_events = defaultdict(list)
        for e in self.events:
            for f in e['faculty']:
                fac_events[f].append(e)

        for fac, ev_list in fac_events.items():
            for d in range(5):
                for t in range(9):
                    row = {}
                    for e in ev_list:
                        eid = e['event_id']
                        dur = e['duration']
                        for start_t in range(max(0, t - dur + 1), t + 1):
                            if (eid, d, start_t) in self.var_map:
                                row[self.var_map[(eid, d, start_t)]] = 1.0
                    if len(row) > 1:
                        row_list.append(row)
                        lhs_list.append(0.0)
                        rhs_list.append(1.0)

        num_rows = len(row_list)
        print(f"[MILP Model] Core Level 0 constraint rows: {num_rows}")
        
        mat = dok_matrix((num_rows, self.num_x_vars), dtype=float)
        for r_idx, row in enumerate(row_list):
            for col_idx, val in row.items():
                mat[r_idx, col_idx] = val

        return mat.tocsc(), np.array(lhs_list), np.array(rhs_list)
