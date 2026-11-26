# Implementation Plan - Stage 9: Timetable Generation & Optimization Engine

## Executive Overview
Stage 9 introduces the production-grade deterministic timetable generation and optimization engine for Woxsen University's Timetable Management Platform. It constructs valid timetable candidates from canonical project requirements, active policy snapshots, and Stage 8.6 feasibility results while strictly respecting all HARD constraints and optimizing SOFT constraints and PREFERENCES.

---

## Strict Boundaries & Non-Goals
1. **Never mutate certified production timetable** (`production_schedule.json`, `production_schedule.csv`, `stage5_3_corrected_optimized_schedule.json`).
2. **Never mutate original FET HTML sources**.
3. **No writing into production directories**: all generated candidate outputs live in isolated directories under `projects/generated/<run_id>/`.
4. **No future scope leakage**: strictly exclude holiday recovery, closure simulation, approval workflows, public publishing, or public timetable viewers.
5. **No solver-less heuristics claiming mathematical proof**: deterministic event domain enumeration, lexicographic multi-stage optimization, bounded backtracking, and candidate scoring.
6. **Hard stop upon Stage 9 certification**.

---

## Technical Architecture & Pipeline
```
LOAD_PROJECT_VERSION
  ↓
LOAD_ACTIVE_POLICY_SNAPSHOT
  ↓
LOAD_FEASIBILITY_RESULT (verify fresh & status in [FEASIBLE, FEASIBLE_WITH_WARNINGS])
  ↓
BUILD_GENERATION_MODEL & FREEZE_HARD_CONSTRAINTS
  ↓
BUILD_EVENT_PLACEMENT_DOMAINS (zero-domain detection -> INFEASIBLE_GENERATION)
  ↓
ORDER_EVENTS (deterministic most-constrained-first ordering)
  ↓
CONSTRUCT_INITIAL_CANDIDATE (incremental indexing & atomic synchronized placement)
  ↓
HARD_CONSTRAINT_VALIDATION & BOUNDED_BACKTRACKING
  ↓
SOFT_CONSTRAINT_SCORING & PREFERENCE_SCORING (Lexicographic P0 -> P6)
  ↓
QUALITY_OPTIMIZATION (profile-based local neighborhood improvement)
  ↓
FINAL_HARD_VALIDATION (Independent parity with validator.py & schedule_editor_service.py)
  ↓
BASELINE_COMPARISON (read-only comparison with Stage 5.3 / project baseline)
  ↓
IMMUTABLE_STORAGE (projects/generated/<run_id>/candidates/candidate_001.json)
```

---

## Proposed Changes

### 1. Generation Engine Core: `generation_models.py`
- `GenerationProfile`: `FEASIBILITY_FIRST`, `BALANCED`, `QUALITY_FIRST`, `STABILITY_FIRST`.
- `GenerationStatus`: `READY`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `INFEASIBLE_GENERATION`, `GENERATION_FAILED`, `TIME_LIMIT`, `CANCELLED`, `ERROR`.
- `PlacementDomain`: legal days/slots per event, blocked reasons, placement count.
- `TimetableCandidate`: candidate ID, project ID, version ID, policy snapshot ID, assignments, hard violation count, soft penalties, preference penalties, gap score, run score, balance score, stability score, overall quality score, validation report, fingerprint.
- `GenerationStatistics`: domain generation time, construction time, optimization time, backtracks, dead ends, placements attempted/accepted/rejected.
- `GenerationResult`: full output contract matching Stage 9 specification.

### 2. Generation Engine Implementation: `generation_engine.py`
- Deterministic event ordering: pinned/frozen first, smallest legal placement domain first, largest number of constrained resources, labs (2-hour contiguous windows), shared multi-section events atomic placement.
- Bounded backtracking engine: respects maximum search depth and time limits.
- Incremental occupancy matrix for section, faculty, room, and special resources.
- Synchronization atomic placement: shared events across multiple sections/faculty placed as atomic tuples.
- Lexicographic multi-stage optimization:
  - P0: Zero HARD violations (mandatory gate)
  - P1: Critical SOFT violations
  - P2: Runs and gaps (minimize exact 5-hour runs, minimize isolated gaps)
  - P3: Daily load balance
  - P4: Lunch and day quality
  - P5: Preference satisfaction
  - P6: Stability against baseline (minimize day changes, then slot displacements, then room changes)
- Parity validation against `validator.py` and Stage 8.5 active policy snapshot.

### 3. Generation Service & Storage: `generation_service.py`
- Server-side RBAC authorization (`SUPER_ADMIN`, `TIMETABLE_ADMIN`, `TEACHER`, `VIEWER`).
- Feasibility freshness guard: verifies Stage 8.6 feasibility result exists, is not stale, and status is `FEASIBLE` or `FEASIBLE_WITH_WARNINGS`.
- Immutable filesystem storage in `projects/generated/<run_id>/`:
  - `generation_request.json`
  - `generation_result.json`
  - `generation_log.json`
  - `input/project_version.json`
  - `input/policy_snapshot.json`
  - `input/feasibility_result.json`
  - `candidates/candidate_001.json`
  - `candidates/candidate_001_validation.json`
  - `candidates/candidate_001_score.json`
  - `comparison/baseline_vs_candidate_001.json`
- Append-only audit logging integration (`GENERATION_STARTED`, `GENERATION_COMPLETED`, `GENERATION_FAILED`, `CANDIDATE_CREATED`, `CANDIDATE_VALIDATED`, `CANDIDATE_SELECTED`).

### 4. Frontend Integration: `index.html`
- Route: `/projects/:project_id/generation`.
- UI Components:
  - Generation workspace with feasibility readiness status and active policy badge.
  - Controls: Generation profile selector, candidate count, seed, time limit, preserve existing assignments toggle.
  - Generation progress state & live statistics.
  - Candidate cards list with hard validation badge, soft score breakdown, before/after comparison table, and interactive candidate timetable preview.
  - Diagnostics and unplaced event breakdown (if infeasible/failed).
  - Project card integration: "Generate" action button and generation status badge on project list.

### 5. Automated Verification Suite: `run_stage9_tests.py`
- Minimum 120 automated tests covering all required categories.
- Mandatory fixtures: `SMALL_FEASIBLE_PROJECT`, `PINNED_EVENT_PROJECT`, `FROZEN_EVENT_PROJECT`, `FACULTY_COLLISION_PROJECT`, `SECTION_COLLISION_PROJECT`, `ROOM_COLLISION_PROJECT`, `LAB_PROJECT`, `SHARED_MULTI_SECTION_PROJECT`, `MULTI_FACULTY_PROJECT`, `SPLIT_NESTED_PROJECT`, `FRIDAY_CLOSURE_PROJECT`, `BLOCKED_TIME_PROJECT`, `ROOM_CAPACITY_PROJECT`, `ZERO_DOMAIN_PROJECT`, `SOFT_OPTIMIZATION_PROJECT`, `STABILITY_PROJECT`, `MULTI_CANDIDATE_PROJECT`.
- Full 598-event certified dataset read-only generation test verifying 748 student-hours, 981 faculty-hours, 75 labs, 38 shared events, 3 NO_ROOM events, Friday closure, and independent validator parity.
- Golden hash preservation tests.

---

## Verification Plan
1. **Unit & Integration Tests**: `python run_stage9_tests.py` (target: 120+ tests, 100% pass).
2. **Preflight & Golden Hashes**: verify `production_schedule.json`, `stage5_3_corrected_optimized_schedule.json`, `production_schedule.csv`, and FET sources.
3. **Certified Dataset Test**: generate candidate for 598-event dataset, validate with `validator.py`.
4. **UI Verification**: ensure `/projects/:id/generation` renders with 0 console errors and responsive layout.
5. **Certification Documentation**: generate `stage_9_implementation_report.json`, `stage_9_implementation_report.md`, `stage_9_test_results.json`, `stage_9_certification_report.json`.
