"""
simulation_service.py - Stage 10 Service Layer & Storage Isolation
Holiday Closure Recovery & Timetable Simulation Engine
"""

import os
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

from auth_service import User, UserRole, AuditEventType, AuthenticationService
from simulation_models import (
    DisruptionScenario,
    AffectedEvent,
    SimulationResult,
    RecoveryCandidate,
    TeachingDeficit,
    compute_hash
)
from simulation_engine import TimetableSimulationEngine

SIMULATIONS_STORAGE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "simulations")

class SimulationService:
    def __init__(
        self,
        engine: Optional[TimetableSimulationEngine] = None,
        auth: Optional[AuthenticationService] = None,
        storage_root: str = SIMULATIONS_STORAGE_ROOT
    ):
        self.engine = engine or TimetableSimulationEngine()
        self.auth = auth or AuthenticationService()
        self.storage_root = storage_root
        os.makedirs(self.storage_root, exist_ok=True)

    def check_authorization(self, user: User, project: Dict[str, Any], action: str) -> Tuple[bool, str]:
        """
        Server-side default-deny RBAC:
        SUPER_ADMIN: all
        TIMETABLE_ADMIN: all on authorized
        TEACHER: only on owned/assigned projects
        VIEWER: strictly read-only
        """
        if user.role in [UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN]:
            return True, "Authorized"

        if user.role == UserRole.TEACHER:
            if project.get("owner_user_id") == user.user_id or project.get("created_by_user_id") == user.user_id:
                return True, "Authorized"
            return False, "Permission Denied: Teacher can only execute simulations on owned projects."

        if user.role == UserRole.VIEWER:
            if action in ["view", "list", "read"]:
                return True, "Authorized (Read-Only)"
            return False, "Permission Denied: Viewer has strictly read-only access."

        return False, "Permission Denied: Default deny."

    def run_simulation_for_user(
        self,
        user: User,
        project: Dict[str, Any],
        active_version_id: str,
        scenarios: List[DisruptionScenario],
        seed: int = 42
    ) -> Tuple[bool, Optional[SimulationResult], str]:
        """
        Executes an isolated simulation for an authorized user, saving immutable outputs to disk.
        """
        proj_id = project.get("project_id", "proj_unknown")

        # 1. Authorization check
        ok, msg = self.check_authorization(user, project, "run_simulation")
        if not ok:
            self.auth.audit.log_event(
                AuditEventType.ACCESS_DENIED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={"action": "run_simulation", "reason": msg}
            )
            return False, None, msg

        # 2. Audit: SIMULATION_STARTED
        sim_id = f"sim_{uuid.uuid4().hex[:10]}"
        self.auth.audit.log_event(
            AuditEventType.SIMULATION_STARTED,
            user_id=user.user_id,
            project_id=proj_id,
            metadata={"simulation_id": sim_id, "scenario_count": len(scenarios)}
        )

        try:
            result = self.engine.run_simulation(
                project=project,
                active_version_id=active_version_id,
                scenarios=scenarios,
                user_id=user.user_id,
                seed=seed
            )

            # 3. Save Immutable Directory Structure
            self._save_immutable_simulation(project, scenarios, result)

            # 4. Audit: SIMULATION_COMPLETED
            self.auth.audit.log_event(
                AuditEventType.SIMULATION_COMPLETED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={
                    "simulation_id": result.simulation_id,
                    "recovery_status": result.recovery_status,
                    "affected_events": len(result.affected_events)
                }
            )

            return True, result, "Simulation completed successfully."

        except Exception as ex:
            self.auth.audit.log_event(
                AuditEventType.SIMULATION_FAILED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={"error": str(ex)}
            )
            return False, None, f"Simulation failed: {str(ex)}"

    def _save_immutable_simulation(
        self,
        project: Dict[str, Any],
        scenarios: List[DisruptionScenario],
        result: SimulationResult
    ):
        """
        Persists immutable directory structure under projects/simulations/<simulation_id>/
        """
        sim_dir = os.path.join(self.storage_root, result.simulation_id)
        if os.path.exists(sim_dir):
            raise ValueError(f"Immutable violation: Simulation directory {result.simulation_id} already exists.")

        subdirs = ["input", "scenarios", "disrupted", "recovery", "validation", "comparison", "exports", "logs"]
        for sub in subdirs:
            os.makedirs(os.path.join(sim_dir, sub), exist_ok=True)

        # 1. simulation_request.json & simulation_result.json
        with open(os.path.join(sim_dir, "simulation_request.json"), "w", encoding="utf-8") as f:
            json.dump({
                "simulation_id": result.simulation_id,
                "project_id": project.get("project_id"),
                "version_id": result.source_project_version_id,
                "scenarios": [s.to_dict() for s in scenarios]
            }, f, indent=2)

        with open(os.path.join(sim_dir, "simulation_result.json"), "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        # 2. scenario.json & source_fingerprint.json
        with open(os.path.join(sim_dir, "scenarios", "scenario.json"), "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in scenarios], f, indent=2)

        with open(os.path.join(sim_dir, "input", "source_fingerprint.json"), "w", encoding="utf-8") as f:
            json.dump({"source_timetable_fingerprint": result.source_timetable_fingerprint}, f, indent=2)

        # 3. disrupted_timetable.json
        source_events = project.get("versions", {}).get(result.source_project_version_id, {}).get("events", project.get("events", []))
        disrupted_tt = self.engine.build_disrupted_timetable(
            source_events,
            [AffectedEvent.from_dict(ae) for ae in result.affected_events]
        )
        with open(os.path.join(sim_dir, "disrupted", "disrupted_timetable.json"), "w", encoding="utf-8") as f:
            json.dump(disrupted_tt, f, indent=2)

        # 4. recovery_candidates.json
        with open(os.path.join(sim_dir, "recovery", "recovery_candidates.json"), "w", encoding="utf-8") as f:
            json.dump(result.recovery_candidates, f, indent=2)

        # 5. validation_results.json
        validation_data = {
            "simulation_id": result.simulation_id,
            "feasibility_status": result.feasibility_status,
            "recovery_status": result.recovery_status,
            "candidate_validations": [
                {
                    "candidate_id": c.get("recovery_candidate_id"),
                    "status": c.get("status"),
                    "hard_validation": c.get("hard_validation")
                }
                for c in result.recovery_candidates
            ]
        }
        with open(os.path.join(sim_dir, "validation", "validation_results.json"), "w", encoding="utf-8") as f:
            json.dump(validation_data, f, indent=2)

        # 6. comparison.json & diagnostics.json
        with open(os.path.join(sim_dir, "comparison", "comparison.json"), "w", encoding="utf-8") as f:
            json.dump(result.comparison, f, indent=2)

        with open(os.path.join(sim_dir, "logs", "diagnostics.json"), "w", encoding="utf-8") as f:
            json.dump(result.diagnostics, f, indent=2)

    def list_simulations_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        sims = []
        if not os.path.exists(self.storage_root):
            return []

        for folder in os.listdir(self.storage_root):
            res_path = os.path.join(self.storage_root, folder, "simulation_result.json")
            if os.path.exists(res_path):
                try:
                    with open(res_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("source_project_id") == project_id:
                            sims.append(data)
                except Exception:
                    pass

        return sorted(sims, key=lambda x: x.get("created_at", ""), reverse=True)
