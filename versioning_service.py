"""
versioning_service.py - Stage 11 Version Lifecycle & Immutable Storage
Review, Versioning & Approval Workflow
"""

import os
import json
import uuid
import copy
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

from auth_service import User, UserRole, AuditEventType, AuthenticationService
from versioning_models import (
    VersionState,
    TimetableVersion,
    VERSION_STATE_CAPABILITIES,
    ALLOWED_TRANSITIONS,
    compute_hash
)

PROJECTS_STORAGE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")

class VersioningService:
    def __init__(
        self,
        auth: Optional[AuthenticationService] = None,
        storage_root: str = PROJECTS_STORAGE_ROOT
    ):
        self.auth = auth or AuthenticationService()
        self.storage_root = storage_root
        os.makedirs(self.storage_root, exist_ok=True)

    def check_authorization(self, user: User, project: Dict[str, Any], action: str) -> Tuple[bool, str]:
        """
        Server-side default deny RBAC:
        SUPER_ADMIN: all
        TIMETABLE_ADMIN: all on assigned
        TEACHER: view, create_draft, edit_draft on owned/assigned
        VIEWER: strictly read-only
        """
        if user.role in [UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN]:
            return True, "Authorized"

        if user.role == UserRole.TEACHER:
            is_owner = (project.get("owner_user_id") == user.user_id or project.get("created_by_user_id") == user.user_id)
            if is_owner:
                if action in ["view", "create_version", "edit_draft", "submit_review"]:
                    return True, "Authorized"
                return False, f"Permission Denied: Teacher cannot perform {action}."
            return False, "Permission Denied: Teacher can only modify owned projects."

        if user.role == UserRole.VIEWER:
            if action in ["view", "list", "read", "view_diff"]:
                return True, "Authorized (Read-Only)"
            return False, f"Permission Denied: Viewer cannot perform {action}."

        return False, "Permission Denied: Default deny."

    def create_version(
        self,
        user: User,
        project: Dict[str, Any],
        events: List[Dict[str, Any]],
        parent_version_id: Optional[str] = None,
        version_label: str = "Draft Version",
        source_type: str = "MANUAL_EDIT",
        source_generation_run_id: Optional[str] = None,
        source_simulation_id: Optional[str] = None,
        source_manual_edit_session_id: Optional[str] = None,
        change_summary: str = "Initial draft"
    ) -> Tuple[bool, Optional[TimetableVersion], str]:
        """
        Creates a new immutable DRAFT timetable version.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_authorization(user, project, "create_version")
        if not ok:
            self.auth.audit.log_event(
                AuditEventType.ACCESS_DENIED,
                user_id=user.user_id,
                project_id=proj_id,
                metadata={"action": "create_version", "reason": msg}
            )
            return False, None, msg

        # Determine version number
        existing_versions = self.list_versions_for_project(proj_id)
        next_ver_num = len(existing_versions) + 1

        v_id = f"ver_{uuid.uuid4().hex[:10]}"
        tt_fp = compute_hash(events)
        canon_fp = compute_hash(project.get("dataset", {}))

        version = TimetableVersion(
            version_id=v_id,
            project_id=proj_id,
            parent_version_id=parent_version_id,
            version_number=next_ver_num,
            version_label=version_label,
            status=VersionState.DRAFT,
            source_type=source_type,
            source_generation_run_id=source_generation_run_id,
            source_simulation_id=source_simulation_id,
            source_manual_edit_session_id=source_manual_edit_session_id,
            timetable_fingerprint=tt_fp,
            canonical_dataset_fingerprint=canon_fp,
            policy_snapshot_id=project.get("policy_version", "polver_default"),
            feasibility_run_id=None,
            validation_run_id=None,
            created_by=user.user_id,
            change_summary=change_summary,
            events=copy.deepcopy(events)
        )

        self._save_immutable_version(proj_id, version)

        self.auth.audit.log_event(
            AuditEventType.VERSION_CREATED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=v_id,
            metadata={"version_number": next_ver_num, "fingerprint": tt_fp}
        )

        return True, version, "Version created successfully."

    def edit_draft_version(
        self,
        user: User,
        project: Dict[str, Any],
        version_id: str,
        updated_events: List[Dict[str, Any]],
        change_summary: str = "Updated draft events"
    ) -> Tuple[bool, Optional[TimetableVersion], str]:
        """
        Edits a DRAFT version. Fails if version is not in DRAFT status.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_authorization(user, project, "edit_draft")
        if not ok:
            return False, None, msg

        version = self.get_version(proj_id, version_id)
        if not version:
            return False, None, f"Version {version_id} not found."

        if version.status != VersionState.DRAFT:
            return False, None, f"Cannot edit version in '{version.status}' state. Only DRAFT is editable."

        version.events = copy.deepcopy(updated_events)
        version.timetable_fingerprint = compute_hash(updated_events)
        version.change_summary = change_summary
        version.metadata["last_edited_by"] = user.user_id
        version.metadata["last_edited_at"] = datetime.now(timezone.utc).isoformat()

        # Update persisted draft
        self._persist_version_metadata(proj_id, version)

        return True, version, "Draft updated successfully."

    def transition_version_state(
        self,
        user: User,
        project: Dict[str, Any],
        version_id: str,
        target_state: str,
        reason: str = ""
    ) -> Tuple[bool, Optional[TimetableVersion], str]:
        """
        Transitions a version through the allowed state machine.
        Rejects forbidden transitions.
        """
        proj_id = project.get("project_id", "proj_unknown")
        version = self.get_version(proj_id, version_id)
        if not version:
            return False, None, f"Version {version_id} not found."

        current_state = version.status

        # Check allowed transitions
        if (current_state, target_state) not in ALLOWED_TRANSITIONS:
            return False, None, f"Illegal transition: Cannot transition version from {current_state} to {target_state}."

        before_state = current_state
        version.status = target_state

        if target_state == VersionState.APPROVED:
            version.approved_at = datetime.now(timezone.utc).isoformat()
            version.locked_at = datetime.now(timezone.utc).isoformat()
        elif target_state == VersionState.SUPERSEDED:
            version.superseded_at = datetime.now(timezone.utc).isoformat()
        elif target_state == VersionState.ARCHIVED:
            version.archived_at = datetime.now(timezone.utc).isoformat()

        self._persist_version_metadata(proj_id, version)

        # Audit transition
        self.auth.audit.log_event(
            AuditEventType.VERSION_READY_FOR_REVIEW if target_state == VersionState.READY_FOR_REVIEW else AuditEventType.PROJECT_UPDATED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=version_id,
            metadata={"before_state": before_state, "after_state": target_state, "reason": reason}
        )

        return True, version, f"Transitioned from {before_state} to {target_state}."

    def _safe_path(self, project_id: str, version_id: str) -> str:
        if ".." in project_id or project_id.startswith("/") or project_id.startswith("\\") or \
           ".." in version_id or version_id.startswith("/") or version_id.startswith("\\"):
            raise ValueError("Invalid project_id or version_id: path traversal detected")
        safe_proj = os.path.basename(project_id).replace("..", "").replace("/", "").replace("\\", "")
        safe_ver = os.path.basename(version_id).replace("..", "").replace("/", "").replace("\\", "")
        if not safe_proj or not safe_ver:
            raise ValueError("Invalid project_id or version_id: path traversal detected")
        return os.path.join(self.storage_root, safe_proj, "versions", safe_ver)

    def _save_immutable_version(self, project_id: str, version: TimetableVersion):
        ver_dir = self._safe_path(project_id, version.version_id)
        if os.path.exists(ver_dir):
            raise ValueError(f"Immutability violation: Version directory {version.version_id} already exists.")
        os.makedirs(ver_dir, exist_ok=True)

        # Save timetable snapshot
        with open(os.path.join(ver_dir, "timetable.json"), "w", encoding="utf-8") as f:
            json.dump(version.events, f, indent=2)

        # Save metadata
        meta = version.to_dict()
        meta.pop("events", None)
        with open(os.path.join(ver_dir, "version_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _persist_version_metadata(self, project_id: str, version: TimetableVersion):
        ver_dir = self._safe_path(project_id, version.version_id)
        os.makedirs(ver_dir, exist_ok=True)
        with open(os.path.join(ver_dir, "timetable.json"), "w", encoding="utf-8") as f:
            json.dump(version.events, f, indent=2)
        meta = version.to_dict()
        meta.pop("events", None)
        with open(os.path.join(ver_dir, "version_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def get_version(self, project_id: str, version_id: str) -> Optional[TimetableVersion]:
        try:
            ver_dir = self._safe_path(project_id, version_id)
        except ValueError:
            return None
        meta_file = os.path.join(ver_dir, "version_metadata.json")
        tt_file = os.path.join(ver_dir, "timetable.json")
        if not os.path.exists(meta_file):
            return None

        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if os.path.exists(tt_file):
            with open(tt_file, "r", encoding="utf-8") as f:
                data["events"] = json.load(f)
        else:
            data["events"] = []

        return TimetableVersion.from_dict(data)

    def list_versions_for_project(self, project_id: str) -> List[TimetableVersion]:
        vers_dir = os.path.join(self.storage_root, project_id, "versions")
        if not os.path.exists(vers_dir):
            return []

        versions = []
        for vid in sorted(os.listdir(vers_dir)):
            ver = self.get_version(project_id, vid)
            if ver:
                versions.append(ver)

        return sorted(versions, key=lambda v: v.version_number)
