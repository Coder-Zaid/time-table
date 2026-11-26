"""
diff_engine.py - Stage 11 Deterministic Timetable Diff Engine
Computes precise event-level differences and movement summaries between two timetables.
"""

from typing import List, Dict, Any, Optional, Set
from versioning_models import DiffSummary, EventDiff, EventMovement

class TimetableDiffEngine:
    @staticmethod
    def _extract_coords(e: Dict[str, Any]) -> tuple:
        day = e.get("day", e.get("day_idx", e.get("baseline_day", -1)))
        slot = e.get("slot", e.get("start_slot", e.get("baseline_slot", -1)))
        dur = e.get("duration", 1)
        room = e.get("room", "NO_ROOM")
        return day, slot, dur, room

    @classmethod
    def compute_diff(
        cls,
        base_events: List[Dict[str, Any]],
        target_events: List[Dict[str, Any]],
        hard_conflicts_before: int = 0,
        hard_conflicts_after: int = 0
    ) -> DiffSummary:
        """
        Computes deterministic, stable event diffs between base and target timetables.
        Preserves lab continuity (both slots viewed as 1 logical movement)
        and shared event synchronizations.
        """
        base_map = {e.get("event_id"): e for e in base_events if "event_id" in e}
        target_map = {e.get("event_id"): e for e in target_events if "event_id" in e}

        all_eids = sorted(list(set(base_map.keys()).union(set(target_map.keys()))), key=lambda x: str(x))

        diff_summary = DiffSummary(
            hard_conflicts_before=hard_conflicts_before,
            hard_conflicts_after=hard_conflicts_after
        )

        event_diffs: List[EventDiff] = []

        for eid in all_eids:
            in_base = eid in base_map
            in_target = eid in target_map

            if not in_base and in_target:
                # Event ADDED
                te = target_map[eid]
                t_day, t_slot, t_dur, t_room = cls._extract_coords(te)
                is_lab = te.get("is_lab", False) or t_dur == 2
                is_shared = len(te.get("sections", [])) > 1

                ed = EventDiff(
                    event_id=eid,
                    subject=te.get("subject", ""),
                    change_type="ADDED",
                    movement=EventMovement(None, t_day, None, t_slot, None, t_room, None, t_dur),
                    is_lab=is_lab,
                    is_shared=is_shared,
                    details="Event newly added"
                )
                event_diffs.append(ed)
                diff_summary.events_added += 1

            elif in_base and not in_target:
                # Event REMOVED
                be = base_map[eid]
                b_day, b_slot, b_dur, b_room = cls._extract_coords(be)
                is_lab = be.get("is_lab", False) or b_dur == 2
                is_shared = len(be.get("sections", [])) > 1

                ed = EventDiff(
                    event_id=eid,
                    subject=be.get("subject", ""),
                    change_type="REMOVED",
                    movement=EventMovement(b_day, None, b_slot, None, b_room, None, b_dur, None),
                    is_lab=is_lab,
                    is_shared=is_shared,
                    details="Event removed"
                )
                event_diffs.append(ed)
                diff_summary.events_removed += 1

            else:
                # Both exist - check for modifications
                be = base_map[eid]
                te = target_map[eid]

                b_day, b_slot, b_dur, b_room = cls._extract_coords(be)
                t_day, t_slot, t_dur, t_room = cls._extract_coords(te)

                is_lab = be.get("is_lab", False) or b_dur == 2 or te.get("is_lab", False) or t_dur == 2
                is_shared = len(be.get("sections", [])) > 1 or len(te.get("sections", [])) > 1

                b_fac = set(be.get("faculty", []))
                t_fac = set(te.get("faculty", []))
                b_sec = set(be.get("sections", []))
                t_sec = set(te.get("sections", []))

                day_changed = (b_day != t_day)
                slot_changed = (b_slot != t_slot)
                room_changed = (b_room != t_room)
                dur_changed = (b_dur != t_dur)
                fac_changed = (b_fac != t_fac)
                sec_changed = (b_sec != t_sec)

                has_moved = day_changed or slot_changed
                is_changed = has_moved or room_changed or dur_changed or fac_changed or sec_changed

                if is_changed:
                    details_parts = []
                    if day_changed:
                        details_parts.append(f"Day: {b_day} -> {t_day}")
                        diff_summary.day_changes += 1
                    if slot_changed:
                        disp = abs(t_slot - b_slot)
                        details_parts.append(f"Slot: {b_slot} -> {t_slot}")
                        diff_summary.total_slot_displacement += disp
                    if room_changed:
                        details_parts.append(f"Room: {b_room} -> {t_room}")
                        diff_summary.rooms_changed += 1
                    if dur_changed:
                        details_parts.append(f"Duration: {b_dur}h -> {t_dur}h")
                    if fac_changed:
                        details_parts.append(f"Faculty updated")
                        diff_summary.faculty_changed += 1
                    if sec_changed:
                        details_parts.append(f"Sections updated")
                        diff_summary.sections_changed += 1

                    if has_moved:
                        diff_summary.events_moved += 1

                    ed = EventDiff(
                        event_id=eid,
                        subject=te.get("subject", be.get("subject", "")),
                        change_type="MOVED" if has_moved else "MODIFIED",
                        movement=EventMovement(b_day, t_day, b_slot, t_slot, b_room, t_room, b_dur, t_dur),
                        faculty_changed=fac_changed,
                        section_changed=sec_changed,
                        room_changed=room_changed,
                        duration_changed=dur_changed,
                        is_lab=is_lab,
                        is_shared=is_shared,
                        details="; ".join(details_parts)
                    )
                    event_diffs.append(ed)

        diff_summary.event_diffs = [ed.to_dict() for ed in event_diffs]
        return diff_summary
