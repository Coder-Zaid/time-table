"""
generation_service.py - Service Layer, RBAC Authorization, Feasibility Freshness Guard,
Audit Logging, and Immutable Filesystem Storage for Stage 9 Timetable Generation Engine
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

import auth_service
from auth_service import User, UserRole, AuditEventType, AuthenticationService
from generation_models import (
    GenerationStatus,
    GenerationProfile,
    GenerationConfig,
    GenerationResult,
    TimetableCandidate
)
from generation_engine import TimetableGenerationEngine

GENERATED_STORAGE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", "generated")

class GenerationService:
    def __init__(
        self,
        engine: Optional[TimetableGenerationEngine] = None,
        auth: Optional[AuthenticationService] = None,
        storage_root: str = GENERATED_STORAGE_ROOT
    ):
        self.engine = engine or TimetableGenerationEngine()
        self.auth = auth or AuthenticationService()
        self.storage_root = storage_root
        os.makedirs(self.storage_root, exist_ok=True)

    def check_feasibility_readiness(
        self,
        project: Dict[str, Any],
        feasibility_result: Optional[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """
        Guards generation against missing, stale, or infeasible Stage 8.6 results.
        """
        if not feasibility_result:
            return False, "Feasibility analysis has not been executed for this project. Successful Stage 8.6 analysis is mandatory before generation."

        status = feasibility_result.get("status")
        if status not in ["FEASIBLE", "FEASIBLE_WITH_WARNINGS"]:
            return False, f"Feasibility status is '{status}'. Generation requires status FEASIBLE or FEASIBLE_WITH_WARNINGS."

        # Version match
        p_ver = project.get("active_version_id", "v1")
        f_ver = feasibility_result.get("project_version_id")
        if f_ver and f_ver != p_ver:
            return False, f"Feasibility result is stale: analyzed for version '{f_ver}' but current active version is '{p_ver}'."

        # Policy snapshot match
        p_pol = project.get("policy_version", "polver_default")
        f_pol = feasibility_result.get("policy_snapshot_id")
        if f_pol and f_pol != p_pol:
            return False, f"Feasibility result is stale: analyzed for policy snapshot '{f_pol}' but current policy snapshot is '{p_pol}'."

        return True, "Feasibility result is fresh and eligible for generation."

    def run_generation_for_user(
        self,
        user: User,
        project: Dict[str, Any],
        feasibility_result: Dict[str, Any],
        config: Optional[GenerationConfig] = None,
        active_version_id: Optional[str] = None,
        policies: Optional[List[Dict[str, Any]]] = None,
        policy_snapshot_id: Optional[str] = None,
        blocked_slots: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Optional[GenerationResult], str]:
        """
        Enforces server-side RBAC, verifies feasibility readiness, records audit trail,
        runs deterministic generation, and writes immutable records to disk.
        """
        proj_id = project.get("project_id", "proj_unknown")

        # 1. RBAC Check
        # SUPER_ADMIN & TIMETABLE_ADMIN can generate on authorized projects
        # TEACHER can generate on owned projects
        # VIEWER cannot generate
        can_generate = False
        if user.role in [UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN]:
            can_generate = True
        elif user.role == UserRole.TEACHER:
            if project.get("owner_user_id") == user.user_id or project.get("created_by_user_id") == user.user_id:
                can_generate = True

        if not can_generate:
            self.auth.audit.log_event(
                AuditEventType.ACCESS_DENIED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={"action": "run_generation", "reason": "Insufficient role or project ownership permissions"}
            )
            return False, None, "Permission denied: You do not have authorization to run timetable generation on this project."

        # 2. Feasibility Readiness Check
        fresh, msg = self.check_feasibility_readiness(project, feasibility_result)
        if not fresh:
            return False, None, f"Generation blocked: {msg}"

        # 3. Audit Event: GENERATION_STARTED
        run_id = config.generation_run_id if config else f"gen_{uuid.uuid4().hex[:12]}"
        cfg = config or GenerationConfig(generation_run_id=run_id)
        self.auth.audit.log_event(
            AuditEventType.GENERATION_STARTED,
            user_id=user.user_id,
            project_id=proj_id,
            metadata={
                "run_id": cfg.generation_run_id,
                "seed": cfg.seed,
                "profile": cfg.optimization_profile,
                "candidate_count": cfg.candidate_count
            }
        )

        try:
            result = self.engine.generate(
                project=project,
                active_version_id=active_version_id,
                policy_snapshot_id=policy_snapshot_id,
                feasibility_run_id=feasibility_result.get("feasibility_run_id"),
                config=cfg,
                policies=policies,
                blocked_slots=blocked_slots,
                user_id=user.user_id
            )

            # Persist immutable records
            self._save_immutable_run(project, feasibility_result, result)

            # Audit Event: GENERATION_COMPLETED
            self.auth.audit.log_event(
                AuditEventType.GENERATION_COMPLETED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={
                    "run_id": result.generation_run_id,
                    "status": result.status,
                    "valid_candidates": result.candidate_count_valid,
                    "selected_candidate_id": result.selected_candidate_id
                }
            )
            return True, result, "Generation completed successfully."
        except Exception as ex:
            self.auth.audit.log_event(
                AuditEventType.GENERATION_FAILED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={"action": "GENERATION_FAILED", "error": str(ex)}
            )
            return False, None, f"Generation failed: {str(ex)}"

    def _save_immutable_run(
        self,
        project: Dict[str, Any],
        feasibility_result: Dict[str, Any],
        result: GenerationResult
    ):
        """
        Persists all artifacts under projects/generated/<generation_run_id>/
        """
        run_dir = os.path.join(self.storage_root, result.generation_run_id)
        if os.path.exists(run_dir):
            raise ValueError(f"Immutable violation: Generation run directory {result.generation_run_id} already exists.")

        subdirs = ["input", "canonical", "feasibility", "candidates", "validation", "comparison", "exports", "logs"]
        for sub in subdirs:
            os.makedirs(os.path.join(run_dir, sub), exist_ok=True)

        # 1. generation_request.json & generation_result.json
        with open(os.path.join(run_dir, "generation_request.json"), "w", encoding="utf-8") as f:
            json.dump(result.configuration, f, indent=2)

        with open(os.path.join(run_dir, "generation_result.json"), "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        # 2. input snapshots
        with open(os.path.join(run_dir, "input", "project_version.json"), "w", encoding="utf-8") as f:
            json.dump({
                "project_id": project.get("project_id"),
                "version_id": result.project_version_id
            }, f, indent=2)

        with open(os.path.join(run_dir, "input", "feasibility_result.json"), "w", encoding="utf-8") as f:
            json.dump(feasibility_result, f, indent=2)

        # 3. candidates
        if result.selected_candidate:
            with open(os.path.join(run_dir, "candidates", "candidate_001.json"), "w", encoding="utf-8") as f:
                json.dump(result.selected_candidate, f, indent=2)

            with open(os.path.join(run_dir, "validation", "candidate_001_validation.json"), "w", encoding="utf-8") as f:
                json.dump(result.validation_summary, f, indent=2)

            with open(os.path.join(run_dir, "comparison", "baseline_vs_candidate_001.json"), "w", encoding="utf-8") as f:
                json.dump(result.comparison_summary, f, indent=2)

        # 4. generation_log.json
        with open(os.path.join(run_dir, "logs", "generation_log.json"), "w", encoding="utf-8") as f:
            json.dump({
                "generation_run_id": result.generation_run_id,
                "timestamp": result.timestamp,
                "statistics": result.generation_statistics.to_dict(),
                "status": result.status
            }, f, indent=2)

    def list_generation_runs_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        runs = []
        if not os.path.exists(self.storage_root):
            return []

        for folder in os.listdir(self.storage_root):
            res_path = os.path.join(self.storage_root, folder, "generation_result.json")
            if os.path.exists(res_path):
                try:
                    with open(res_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("project_id") == project_id:
                            runs.append(data)
                except Exception:
                    pass

        return sorted(runs, key=lambda x: x.get("timestamp", ""), reverse=True)
