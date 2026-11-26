"""
review_service.py - Stage 11 Review Workflow & Change Requests
Review, Versioning & Approval Workflow
"""

import os
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

from auth_service import User, UserRole, AuditEventType, AuthenticationService
from versioning_models import (
    VersionState,
    ReviewStatus,
    ReviewDecision,
    CommentSeverity,
    CommentStatus,
    ChangeRequestStatus,
    ChangeRequestPriority,
    ReviewRecord,
    ReviewComment,
    ChangeRequest
)
from versioning_service import VersioningService

class ReviewService:
    def __init__(
        self,
        versioning_svc: Optional[VersioningService] = None,
        auth: Optional[AuthenticationService] = None
    ):
        self.versioning = versioning_svc or VersioningService()
        self.auth = auth or AuthenticationService()
        self.storage_root = self.versioning.storage_root

    def check_review_authorization(self, user: User, project: Dict[str, Any], action: str) -> Tuple[bool, str]:
        """
        RBAC for review:
        SUPER_ADMIN, TIMETABLE_ADMIN: all review actions
        TEACHER: submit review comments & responses
        VIEWER: strictly read-only
        """
        if user.role in [UserRole.SUPER_ADMIN, UserRole.TIMETABLE_ADMIN]:
            return True, "Authorized"

        if user.role == UserRole.TEACHER:
            if action in ["view", "add_comment", "respond_change_request"]:
                return True, "Authorized"
            return False, f"Permission Denied: Teacher cannot execute review decision '{action}'."

        if user.role == UserRole.VIEWER:
            if action in ["view", "list"]:
                return True, "Authorized (Read-Only)"
            return False, "Permission Denied: Viewer cannot modify review records."

        return False, "Permission Denied: Default deny."

    def start_review(
        self,
        user: User,
        project: Dict[str, Any],
        version_id: str
    ) -> Tuple[bool, Optional[ReviewRecord], str]:
        """
        Initiates a formal review session on a READY_FOR_REVIEW version, moving it to IN_REVIEW.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_review_authorization(user, project, "start_review")
        if not ok:
            return False, None, msg

        version = self.versioning.get_version(proj_id, version_id)
        if not version:
            return False, None, f"Version {version_id} not found."

        if version.status not in [VersionState.READY_FOR_REVIEW, VersionState.CHANGES_REQUESTED]:
            return False, None, f"Cannot start review on version in state '{version.status}'. Expected READY_FOR_REVIEW."

        # Transition version to IN_REVIEW
        ok_t, _, t_msg = self.versioning.transition_version_state(user, project, version_id, VersionState.IN_REVIEW, reason="Review started")
        if not ok_t:
            return False, None, t_msg

        rev_id = f"rev_{uuid.uuid4().hex[:10]}"
        review = ReviewRecord(
            review_id=rev_id,
            project_id=proj_id,
            version_id=version_id,
            reviewer_user_id=user.user_id,
            reviewer_role=user.role,
            status=ReviewStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc).isoformat()
        )

        self._save_review(proj_id, review)

        self.auth.audit.log_event(
            AuditEventType.REVIEW_STARTED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=version_id,
            metadata={"review_id": rev_id}
        )

        return True, review, "Review started successfully."

    def add_comment(
        self,
        user: User,
        project: Dict[str, Any],
        review_id: str,
        body: str,
        severity: str = CommentSeverity.INFO,
        event_id: Optional[Any] = None,
        section_id: Optional[str] = None,
        faculty_id: Optional[str] = None,
        room_id: Optional[str] = None
    ) -> Tuple[bool, Optional[ReviewComment], str]:
        """
        Adds a comment to an active review.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_review_authorization(user, project, "add_comment")
        if not ok:
            return False, None, msg

        review = self.get_review(proj_id, review_id)
        if not review:
            return False, None, f"Review {review_id} not found."

        if review.status != ReviewStatus.IN_PROGRESS:
            return False, None, f"Cannot add comments to review in status '{review.status}'."

        c_id = f"com_{uuid.uuid4().hex[:10]}"
        comment = ReviewComment(
            comment_id=c_id,
            review_id=review_id,
            version_id=review.version_id,
            event_id=event_id,
            section_id=section_id,
            faculty_id=faculty_id,
            room_id=room_id,
            author_user_id=user.user_id,
            body=body,
            severity=severity,
            status=CommentStatus.OPEN
        )

        review.comments.append(comment.to_dict())
        self._save_review(proj_id, review)

        self.auth.audit.log_event(
            AuditEventType.REVIEW_COMMENT_CREATED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=review.version_id,
            metadata={"comment_id": c_id, "severity": severity, "review_id": review_id}
        )

        return True, comment, "Comment added successfully."

    def resolve_comment(
        self,
        user: User,
        project: Dict[str, Any],
        review_id: str,
        comment_id: str,
        dismiss: bool = False
    ) -> Tuple[bool, str]:
        """
        Resolves or dismisses a review comment.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_review_authorization(user, project, "resolve_comment")
        if not ok:
            return False, msg

        review = self.get_review(proj_id, review_id)
        if not review:
            return False, f"Review {review_id} not found."

        target_c = None
        for c in review.comments:
            if c.get("comment_id") == comment_id:
                target_c = c
                break

        if not target_c:
            return False, f"Comment {comment_id} not found."

        target_c["status"] = CommentStatus.DISMISSED if dismiss else CommentStatus.RESOLVED
        target_c["resolved_at"] = datetime.now(timezone.utc).isoformat()
        target_c["resolved_by"] = user.user_id

        self._save_review(proj_id, review)

        self.auth.audit.log_event(
            AuditEventType.REVIEW_COMMENT_DISMISSED if dismiss else AuditEventType.REVIEW_COMMENT_RESOLVED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=review.version_id,
            metadata={"comment_id": comment_id, "review_id": review_id}
        )

        return True, f"Comment {comment_id} marked as {target_c['status']}."

    def create_change_request(
        self,
        user: User,
        project: Dict[str, Any],
        review_id: str,
        reason: str,
        priority: str = ChangeRequestPriority.MEDIUM,
        assigned_to: Optional[str] = None,
        affected_event_ids: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[ChangeRequest], str]:
        """
        Logs a formal change request linked to a review.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_review_authorization(user, project, "create_change_request")
        if not ok:
            return False, None, msg

        review = self.get_review(proj_id, review_id)
        if not review:
            return False, None, f"Review {review_id} not found."

        cr_id = f"cr_{uuid.uuid4().hex[:10]}"
        cr = ChangeRequest(
            change_request_id=cr_id,
            project_id=proj_id,
            source_version_id=review.version_id,
            target_version_id=None,
            requested_by=user.user_id,
            assigned_to=assigned_to,
            reason=reason,
            priority=priority,
            status=ChangeRequestStatus.OPEN,
            affected_event_ids=affected_event_ids or []
        )

        review.change_requests.append(cr.to_dict())
        self._save_review(proj_id, review)

        self.auth.audit.log_event(
            AuditEventType.CHANGE_REQUEST_CREATED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=review.version_id,
            metadata={"change_request_id": cr_id, "priority": priority}
        )

        return True, cr, "Change request created."

    def complete_review(
        self,
        user: User,
        project: Dict[str, Any],
        review_id: str,
        decision: str,
        summary: str = ""
    ) -> Tuple[bool, Optional[ReviewRecord], str]:
        """
        Completes a review session.
        If decision is APPROVE_FOR_APPROVAL: transitions version to READY_FOR_APPROVAL (if no blocking comments).
        If decision is REQUEST_CHANGES: transitions version to CHANGES_REQUESTED.
        """
        proj_id = project.get("project_id", "proj_unknown")
        ok, msg = self.check_review_authorization(user, project, "complete_review")
        if not ok:
            return False, None, msg

        review = self.get_review(proj_id, review_id)
        if not review:
            return False, None, f"Review {review_id} not found."

        if decision not in [ReviewDecision.APPROVE_FOR_APPROVAL, ReviewDecision.REQUEST_CHANGES, ReviewDecision.REJECT]:
            return False, None, f"Invalid decision: {decision}"

        # If approving for approval, verify zero unresolved BLOCKING comments
        unresolved_blocking = [
            c for c in review.comments
            if c.get("severity") == CommentSeverity.BLOCKING and c.get("status") == CommentStatus.OPEN
        ]
        if decision == ReviewDecision.APPROVE_FOR_APPROVAL and unresolved_blocking:
            return False, None, f"Cannot approve for approval: {len(unresolved_blocking)} unresolved BLOCKING comment(s) exist."

        review.status = ReviewStatus.COMPLETED
        review.completed_at = datetime.now(timezone.utc).isoformat()
        review.decision = decision
        review.summary = summary

        # Target version transition
        target_state = VersionState.READY_FOR_APPROVAL if decision == ReviewDecision.APPROVE_FOR_APPROVAL else VersionState.CHANGES_REQUESTED
        ok_t, _, t_msg = self.versioning.transition_version_state(user, project, review.version_id, target_state, reason=f"Review completed: {decision}")
        if not ok_t:
            return False, None, t_msg

        self._save_review(proj_id, review)

        self.auth.audit.log_event(
            AuditEventType.REVIEW_COMPLETED,
            user_id=user.user_id,
            project_id=proj_id,
            version_id=review.version_id,
            metadata={"review_id": review_id, "decision": decision}
        )

        return True, review, f"Review completed with decision '{decision}'."

    def _save_review(self, project_id: str, review: ReviewRecord):
        rev_dir = os.path.join(self.storage_root, project_id, "reviews", review.review_id)
        os.makedirs(rev_dir, exist_ok=True)
        with open(os.path.join(rev_dir, "review.json"), "w", encoding="utf-8") as f:
            json.dump(review.to_dict(), f, indent=2)

    def get_review(self, project_id: str, review_id: str) -> Optional[ReviewRecord]:
        rev_file = os.path.join(self.storage_root, project_id, "reviews", review_id, "review.json")
        if not os.path.exists(rev_file):
            return None
        with open(rev_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ReviewRecord.from_dict(data)

    def list_reviews_for_version(self, project_id: str, version_id: str) -> List[ReviewRecord]:
        revs_dir = os.path.join(self.storage_root, project_id, "reviews")
        if not os.path.exists(revs_dir):
            return []
        reviews = []
        for rid in sorted(os.listdir(revs_dir)):
            r = self.get_review(project_id, rid)
            if r and r.version_id == version_id:
                reviews.append(r)
        return reviews
