"""Approval service for Sprint 7.

Manages approval requests with:
- Console inbox UI
- Slack integration
- 4h expiry with auto-escalation
- SSO identity mapping
- Audit trail
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"


class ApprovalPriority(str, Enum):
    """Priority levels for approval requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ApprovalRequest:
    """An approval request."""

    id: str
    tenant_id: str
    action_id: str
    action_type: str
    arguments: dict[str, Any]
    context: dict[str, Any]

    status: ApprovalStatus
    priority: ApprovalPriority

    requested_by: str = "triage_agent"
    assigned_to: str | None = None
    decided_by: str | None = None

    created_at: datetime = None
    expires_at: datetime = None
    decided_at: datetime | None = None
    escalated_at: datetime | None = None

    decision: bool | None = None
    decision_reason: str | None = None

    audit_trail: list[dict[str, Any]] = None

    def __post_init__(self):
        """Initialize defaults."""
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.expires_at is None:
            self.expires_at = datetime.utcnow() + timedelta(hours=4)
        if self.audit_trail is None:
            self.audit_trail = []

    def is_expired(self) -> bool:
        """Check if request has expired."""
        return datetime.utcnow() > self.expires_at and self.status == ApprovalStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        d["created_at"] = self.created_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat()
        if self.decided_at:
            d["decided_at"] = self.decided_at.isoformat()
        if self.escalated_at:
            d["escalated_at"] = self.escalated_at.isoformat()
        return d


class ApprovalService:
    """Service for managing approval requests and decisions."""

    def __init__(self, db_session, slack_client=None):
        """Initialize approval service.

        Args:
            db_session: Database session
            slack_client: Optional Slack client for notifications
        """
        self.db_session = db_session
        self.slack_client = slack_client
        self.pending_requests: dict[str, ApprovalRequest] = {}  # In-memory store for testing

    async def create_request(
        self,
        action_id: str,
        tenant_id: str,
        action_type: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
        expires_at: datetime | None = None,
        priority: ApprovalPriority = ApprovalPriority.MEDIUM,
    ) -> dict[str, Any]:
        """Create an approval request.

        Args:
            action_id: ID of the action needing approval
            tenant_id: Tenant ID
            action_type: Type of action
            arguments: Action arguments
            context: Additional context
            expires_at: When request expires (default: 4h from now)
            priority: Priority level

        Returns:
            Dictionary with approval request details
        """
        request_id = str(uuid.uuid4())

        if expires_at is None:
            expires_at = datetime.utcnow() + timedelta(hours=4)

        request = ApprovalRequest(
            id=request_id,
            tenant_id=tenant_id,
            action_id=action_id,
            action_type=action_type,
            arguments=arguments,
            context=context,
            status=ApprovalStatus.PENDING,
            priority=priority,
            expires_at=expires_at,
        )

        # Persist request
        self.pending_requests[request_id] = request
        request.audit_trail.append({
            "event": "created",
            "timestamp": datetime.utcnow().isoformat(),
            "priority": priority.value,
        })

        log.info(
            "approval_request_created",
            request_id=request_id,
            action_id=action_id,
            action_type=action_type,
            priority=priority.value,
        )

        # Notify Slack if client available
        if self.slack_client:
            await self._notify_slack_approval(request)

        return request.to_dict()

    async def _notify_slack_approval(self, request: ApprovalRequest) -> None:
        """Send approval request to Slack.

        Args:
            request: Approval request
        """
        try:
            message = {
                "text": f"Approval needed: {request.action_type}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{request.action_type.upper()} approval request*\n_Request ID: {request.id}_",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Action:*\n{request.action_type}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Priority:*\n{request.priority.value}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Expires:*\n{request.expires_at.isoformat()}",
                            },
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{request.arguments!s}```",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Approve",
                                },
                                "value": f"approve_{request.id}",
                                "style": "primary",
                                "action_id": f"approve_{request.id}",
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Reject",
                                },
                                "value": f"reject_{request.id}",
                                "style": "danger",
                                "action_id": f"reject_{request.id}",
                            },
                        ],
                    },
                ],
            }

            await self.slack_client.chat_postMessage(
                channel="approval-inbox",
                **message,
            )

            log.info("approval_slack_notification_sent", request_id=request.id)

        except Exception as e:
            log.error("approval_slack_notification_error", request_id=request.id, error=str(e))

    async def decide(
        self,
        request_id: str,
        approved: bool,
        actor_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Approve or reject an approval request.

        Args:
            request_id: ID of the approval request
            approved: True to approve, False to reject
            actor_id: ID of approver
            reason: Optional reason for decision

        Returns:
            Updated approval request
        """
        request = self.pending_requests.get(request_id)
        if not request:
            log.error("approval_request_not_found", request_id=request_id)
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status != ApprovalStatus.PENDING:
            log.warning(
                "approval_already_decided",
                request_id=request_id,
                status=request.status,
            )
            raise ValueError(f"Request already {request.status.value}")

        # Record decision
        request.decision = approved
        request.decided_by = actor_id
        request.decided_at = datetime.utcnow()
        request.decision_reason = reason or ("Approved" if approved else "Rejected")
        request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED

        request.audit_trail.append({
            "event": "decided",
            "timestamp": datetime.utcnow().isoformat(),
            "actor_id": actor_id,
            "decision": "approved" if approved else "rejected",
            "reason": request.decision_reason,
        })

        log.info(
            "approval_decided",
            request_id=request_id,
            decision="approved" if approved else "rejected",
            actor_id=actor_id,
        )

        return request.to_dict()

    async def wait_for_decision(
        self,
        approval_request_id: str,
        timeout_seconds: int = 14400,
    ) -> dict[str, Any]:
        """Wait for a decision on an approval request (blocking call).

        In a real system with Temporal, this would use signals or conditions.
        For testing, this polls the request status.

        Args:
            approval_request_id: ID of approval request
            timeout_seconds: Max time to wait

        Returns:
            Dictionary with decision (approved, actor_id, timestamp)
        """
        import asyncio

        start_time = datetime.utcnow()
        poll_interval = 1  # seconds

        while True:
            request = self.pending_requests.get(approval_request_id)
            if not request:
                raise ValueError(f"Approval request not found: {approval_request_id}")

            # Check if decided
            if request.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
                return {
                    "approved": request.decision,
                    "actor_id": request.decided_by,
                    "timestamp": request.decided_at.isoformat(),
                }

            # Check expiry
            if request.is_expired():
                request.status = ApprovalStatus.EXPIRED
                request.audit_trail.append({
                    "event": "expired",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                await self._escalate_request(request)

                return {
                    "approved": False,
                    "actor_id": "system",
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Check timeout
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                log.warning(
                    "approval_wait_timeout",
                    request_id=approval_request_id,
                    elapsed_seconds=elapsed,
                )
                raise TimeoutError(f"Approval decision timeout after {elapsed}s")

            # Poll
            await asyncio.sleep(poll_interval)

    async def _escalate_request(self, request: ApprovalRequest) -> None:
        """Escalate a request after auto-expiry.

        Args:
            request: Approval request
        """
        request.status = ApprovalStatus.ESCALATED
        request.escalated_at = datetime.utcnow()

        request.audit_trail.append({
            "event": "escalated",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Auto-escalation after 4-hour expiry",
        })

        log.warning(
            "approval_auto_escalated",
            request_id=request.id,
            action_type=request.action_type,
        )

        # In production: create escalation ticket, notify managers
        if self.slack_client:
            try:
                await self.slack_client.chat_postMessage(
                    channel="escalation-channel",
                    text=f"Approval escalation: {request.action_type} (Request {request.id})",
                )
            except Exception as e:
                log.error("escalation_notification_error", error=str(e))

    async def get_request(self, request_id: str) -> dict[str, Any] | None:
        """Get approval request by ID.

        Args:
            request_id: ID of approval request

        Returns:
            Approval request dictionary or None
        """
        request = self.pending_requests.get(request_id)
        return request.to_dict() if request else None

    async def list_pending(self, tenant_id: str) -> list[dict[str, Any]]:
        """List all pending approval requests for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of approval requests
        """
        pending = [
            r.to_dict()
            for r in self.pending_requests.values()
            if r.tenant_id == tenant_id and r.status == ApprovalStatus.PENDING
        ]
        return pending

    async def handle_slack_interaction(
        self,
        interaction_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle Slack interactive button action.

        Args:
            interaction_payload: Slack interaction payload

        Returns:
            Response dictionary
        """
        action_id = interaction_payload.get("actions", [{}])[0].get("action_id", "")
        user_id = interaction_payload.get("user", {}).get("id")

        if action_id.startswith("approve_"):
            request_id = action_id.replace("approve_", "")
            await self.decide(request_id, approved=True, actor_id=user_id, reason="Approved via Slack")
            return {"response_type": "in_channel", "text": f"Approved by <@{user_id}>"}

        elif action_id.startswith("reject_"):
            request_id = action_id.replace("reject_", "")
            await self.decide(request_id, approved=False, actor_id=user_id, reason="Rejected via Slack")
            return {"response_type": "in_channel", "text": f"Rejected by <@{user_id}>"}

        return {"response_type": "ephemeral", "text": "Unknown action"}
