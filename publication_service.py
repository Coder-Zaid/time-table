"""
publication_service.py - Stage 12 Publishing Pipeline & Lifecycle Management
Governs publication eligibility, immutable snapshot creation, unpublishing, republishing,
RBAC enforcement, and audit trail integration.
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from publication_models import (
    PublicationRecord,
    PublicationStatus,
    Visibility,
    compute_hash
)
from public_snapshot_service import (
    build_public_timetable_snapshot,
    write_publication_storage
)
from versioning_models import VersionState, TimetableVersion
from auth_service import UserRole, AuditEventType

PUBLISHING_ROLES = {UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN}

class PublicationService:
    def __init__(self, base_dir: str, auth_service=None, versioning_service=None):
        self.base_dir = base_dir
        self.auth_service = auth_service
        self.versioning_service = versioning_service
        self.published_root = os.path.join(self.base_dir, "projects", "published")
        os.makedirs(self.published_root, exist_ok=True)
        self.publications_index_file = os.path.join(self.published_root, "publications_registry.json")
        self._init_registry()

    def _init_registry(self):
        if not os.path.exists(self.publications_index_file):
            with open(self.publications_index_file, "w", encoding="utf-8") as f:
                json.dump({"publications": []}, f, indent=2)

    def _load_registry(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.publications_index_file):
            return []
        try:
            with open(self.publications_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("publications", [])
        except Exception:
            return []

    def _save_registry(self, pubs: List[Dict[str, Any]]):
        with open(self.publications_index_file, "w", encoding="utf-8") as f:
            json.dump({"publications": pubs}, f, indent=2)

    def _log_audit(self, event_type: str, actor_user_id: str, project_id: str, details: Dict[str, Any]):
        if self.auth_service:
            try:
                self.auth_service.log_security_event(
                    event_type=event_type,
                    user_id=actor_user_id,
                    project_id=project_id,
                    details=details
                )
            except Exception:
                pass

    def check_eligibility(
        self,
        version: TimetableVersion,
        user_role: str,
        active_feasibility_run_id: Optional[str] = None,
        is_stale_feasibility: bool = False,
        has_blocking_reviews: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validates all publishing eligibility rules.
        Rejects DRAFT, VALIDATING, IN_REVIEW, CHANGES_REQUESTED, READY_FOR_APPROVAL, SUPERSEDED, ARCHIVED,
        stale fingerprints, stale feasibility, unresolved blocking reviews, and unauthorized roles.
        """
        reasons = []

        # 1. RBAC check
        if user_role not in PUBLISHING_ROLES:
            reasons.append(f"Role '{user_role}' is not authorized to publish timetables. Only SUPER_ADMIN and TIMETABLE_ADMIN may publish.")

        # 2. Version status check
        if version.status != VersionState.APPROVED:
            reasons.append(f"Source version status is '{version.status}'. Only APPROVED versions may be published.")

        # 3. Source immutability / locked status
        if not version.locked_at and version.status != VersionState.APPROVED:
            reasons.append("Source version is not locked/immutable.")

        # 4. Fingerprint freshness check
        current_events_fp = compute_hash(version.events)
        if current_events_fp != version.timetable_fingerprint:
            reasons.append(f"Stale approval detected: timetable events hash ({current_events_fp[:8]}) does not match approved fingerprint ({version.timetable_fingerprint[:8]}).")

        # 5. Feasibility freshness
        if is_stale_feasibility:
            reasons.append("Feasibility analysis result is stale or out of date with current timetable constraints.")

        # 6. Unresolved blocking review comments or change requests
        if has_blocking_reviews:
            reasons.append("Unresolved blocking review comments or change requests exist for this version.")

        # 7. Check if version is archived
        if version.status == VersionState.ARCHIVED or version.archived_at:
            reasons.append("Source version is archived.")

        # 8. Check if version is superseded
        if version.status == VersionState.SUPERSEDED or version.superseded_at:
            reasons.append("Source version has been superseded by a newer version.")

        return len(reasons) == 0, reasons

    def publish_version(
        self,
        version: TimetableVersion,
        user_id: str,
        user_role: str,
        title: str = "Woxsen Academic Timetable",
        description: str = "",
        institution_name: str = "Woxsen University",
        academic_period: str = "Spring 2026",
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
        visibility: str = Visibility.PUBLIC,
        active_feasibility_run_id: Optional[str] = None,
        is_stale_feasibility: bool = False,
        has_blocking_reviews: bool = False
    ) -> Dict[str, Any]:
        """
        Publishes an approved version.
        Creates an immutable public snapshot in projects/published/<pub_id>/
        Automatically marks previously published active publications for this project as SUPERSEDED.
        """
        eligible, reasons = self.check_eligibility(
            version=version,
            user_role=user_role,
            active_feasibility_run_id=active_feasibility_run_id,
            is_stale_feasibility=is_stale_feasibility,
            has_blocking_reviews=has_blocking_reviews
        )
        if not eligible:
            self._log_audit(
                "PUBLIC_PUBLICATION_ACCESS_DENIED",
                user_id,
                version.project_id,
                {"reasons": reasons, "version_id": version.version_id}
            )
            return {
                "success": False,
                "error": "Publication eligibility failed",
                "reasons": reasons
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        pub_id = f"pub_{uuid.uuid4().hex[:12]}"
        public_slug = f"tt-{uuid.uuid4().hex[:8]}"

        # Create PublicationRecord
        record = PublicationRecord(
            publication_id=pub_id,
            public_identifier=pub_id,
            public_slug=public_slug,
            project_id=version.project_id,
            source_version_id=version.version_id,
            source_version_number=version.version_number,
            source_version_fingerprint=version.timetable_fingerprint,
            source_policy_snapshot_id=version.policy_snapshot_id,
            source_feasibility_run_id=version.feasibility_run_id or active_feasibility_run_id,
            source_validation_fingerprint=version.validation_run_id,
            published_at=now_iso,
            published_by=user_id,
            status=PublicationStatus.PUBLISHED,
            visibility=visibility,
            title=title,
            description=description,
            institution_name=institution_name,
            academic_period=academic_period,
            effective_from=effective_from or "2026-01-05",
            effective_to=effective_to or "2026-05-30"
        )

        # Build public snapshot (completely isolated, sanitized)
        snapshot = build_public_timetable_snapshot(
            publication_id=pub_id,
            public_slug=public_slug,
            title=title,
            institution_name=institution_name,
            academic_period=academic_period,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            published_at=now_iso,
            raw_events=version.events
        )

        # Write immutable storage artifacts
        pub_path, snap_path, sha_path, index_path = write_publication_storage(
            base_storage_dir=self.base_dir,
            publication_id=pub_id,
            publication_record_dict=record.to_dict(),
            snapshot=snapshot
        )

        # Mark prior published records for this project as SUPERSEDED in registry
        registry = self._load_registry()
        for p in registry:
            if p["project_id"] == version.project_id and p["status"] == PublicationStatus.PUBLISHED and p["publication_id"] != pub_id:
                p["status"] = PublicationStatus.SUPERSEDED
                p["superseded_by"] = pub_id
                p["updated_at"] = now_iso
                # Update individual record file as well
                prior_pub_file = os.path.join(self.published_root, p["publication_id"], "publication.json")
                if os.path.exists(prior_pub_file):
                    try:
                        with open(prior_pub_file, "r", encoding="utf-8") as f:
                            pf_data = json.load(f)
                        pf_data["status"] = PublicationStatus.SUPERSEDED
                        pf_data["superseded_by"] = pub_id
                        pf_data["updated_at"] = now_iso
                        with open(prior_pub_file, "w", encoding="utf-8") as f:
                            json.dump(pf_data, f, indent=2)
                    except Exception:
                        pass
                self._log_audit(
                    "PUBLICATION_SUPERSEDED",
                    user_id,
                    version.project_id,
                    {"publication_id": p["publication_id"], "superseded_by": pub_id}
                )

        registry.append(record.to_dict())
        self._save_registry(registry)

        # Audit events
        self._log_audit("PUBLICATION_CREATED", user_id, version.project_id, {"publication_id": pub_id})
        self._log_audit("PUBLICATION_PUBLISHED", user_id, version.project_id, {
            "publication_id": pub_id,
            "public_slug": public_slug,
            "source_version_id": version.version_id,
            "source_version_fingerprint": version.timetable_fingerprint,
            "snapshot_fingerprint": snapshot.fingerprint
        })

        return {
            "success": True,
            "publication": record.to_dict(),
            "public_slug": public_slug,
            "public_url": f"/public/{public_slug}",
            "snapshot_fingerprint": snapshot.fingerprint,
            "total_events": snapshot.total_events
        }

    def unpublish(self, publication_id: str, user_id: str, user_role: str, reason: str = "") -> Dict[str, Any]:
        """
        Unpublishes a publication. Does NOT mutate the snapshot.json or delete data.
        Sets status to UNPUBLISHED.
        """
        if user_role not in PUBLISHING_ROLES:
            return {"success": False, "error": f"Role '{user_role}' unauthorized to unpublish."}

        registry = self._load_registry()
        pub_entry = None
        for p in registry:
            if p["publication_id"] == publication_id:
                pub_entry = p
                break

        if not pub_entry:
            return {"success": False, "error": f"Publication '{publication_id}' not found."}

        now_iso = datetime.now(timezone.utc).isoformat()
        pub_entry["status"] = PublicationStatus.UNPUBLISHED
        pub_entry["unpublished_at"] = now_iso
        pub_entry["unpublished_by"] = user_id
        pub_entry["updated_at"] = now_iso
        self._save_registry(registry)

        # Update disk file
        pub_file = os.path.join(self.published_root, publication_id, "publication.json")
        if os.path.exists(pub_file):
            try:
                with open(pub_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["status"] = PublicationStatus.UNPUBLISHED
                data["unpublished_at"] = now_iso
                data["unpublished_by"] = user_id
                data["updated_at"] = now_iso
                with open(pub_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        self._log_audit("PUBLICATION_UNPUBLISHED", user_id, pub_entry["project_id"], {
            "publication_id": publication_id,
            "reason": reason
        })

        return {"success": True, "publication_id": publication_id, "status": PublicationStatus.UNPUBLISHED}

    def republish(
        self,
        new_approved_version: TimetableVersion,
        user_id: str,
        user_role: str,
        previous_publication_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Republishes by creating a brand new isolated publication record and snapshot from a new approved version.
        Never mutates the previous publication or snapshot.
        """
        # If previous_publication_id provided, fetch metadata defaults
        prev_title = "Woxsen Academic Timetable"
        if previous_publication_id:
            for p in self._load_registry():
                if p["publication_id"] == previous_publication_id:
                    prev_title = p.get("title", prev_title)
                    break

        res = self.publish_version(
            version=new_approved_version,
            user_id=user_id,
            user_role=user_role,
            title=title or prev_title
        )
        return res

    def list_publications_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        registry = self._load_registry()
        return [p for p in registry if p["project_id"] == project_id]

    def get_publication(self, publication_id: str) -> Optional[Dict[str, Any]]:
        registry = self._load_registry()
        for p in registry:
            if p["publication_id"] == publication_id:
                return p
        return None

    def get_publication_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        registry = self._load_registry()
        for p in registry:
            if p["public_slug"] == slug:
                return p
        return None

    def get_public_snapshot_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        pub = self.get_publication_by_slug(slug)
        if not pub:
            return None
        # Check publication status
        if pub.get("status") not in (PublicationStatus.PUBLISHED, PublicationStatus.SUPERSEDED):
            return {"error": "UNAVAILABLE", "status": pub.get("status")}

        pub_id = pub["publication_id"]
        snap_file = os.path.join(self.published_root, pub_id, "snapshot.json")
        if not os.path.exists(snap_file):
            return None

        with open(snap_file, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)

        # Integrity verification
        sha_file = os.path.join(self.published_root, pub_id, "snapshot.sha256")
        if os.path.exists(sha_file):
            with open(sha_file, "r", encoding="utf-8") as sf:
                expected_sha = sf.read().strip()
            snap_bytes = json.dumps(snapshot_data, sort_keys=True, separators=(',', ':')).encode('utf-8')
            import hashlib
            actual_sha = hashlib.sha256(snap_bytes).hexdigest()
            if actual_sha != expected_sha:
                return {"error": "SNAPSHOT_INTEGRITY_COMPROMISED"}

        snapshot_data["status"] = pub.get("status")
        snapshot_data["visibility"] = pub.get("visibility")
        return snapshot_data
