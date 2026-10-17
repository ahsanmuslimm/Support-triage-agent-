"""Temporal write action workflow for Sprint 7.

8-state machine:
proposed → policy → approval → executing → retry → succeeded/failed → compensating
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class WriteActionState(str, Enum):
    """States in the write action workflow."""

    PROPOSED = "proposed"
    POLICY_REVIEW = "policy_review"
    APPROVAL_PENDING = "approval_pending"
    EXECUTING = "executing"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATING = "compensating"


class WriteActionType(str, Enum):
    """Types of write actions supported in Sprint 7."""

    REFUND = "refund"
    RETURN_RMA = "return_rma"
    CANCEL_ORDER = "cancel_order"
    ADDRESS_CHANGE = "address_change"
    PASSWORD_RESET = "password_reset"
    PLAN_CHANGE = "plan_change"


@dataclass
class WriteActionInput:
    """Input to a write action."""

    tenant_id: str
    customer_id: str
    action_type: WriteActionType
    intent_name: str
    intent_confidence: float
    arguments: dict[str, Any]
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context: dict[str, Any] = field(default_factory=dict)
    autonomy_level: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    message_id: str | None = None
    conversation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["action_type"] = self.action_type.value
        d["created_at"] = self.created_at.isoformat()
        return d


@dataclass
class WriteActionContext:
    """Context maintained during workflow execution."""

    input: WriteActionInput
    state: WriteActionState
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Policy evaluation
    policy_approved: bool = False
    policy_reason: str = ""
    policy_guardrails_triggered: list[str] = field(default_factory=list)

    # Approval
    approval_required: bool = False
    approval_actor_id: str | None = None
    approval_decision: bool | None = None
    approval_timestamp: datetime | None = None
    approval_expires_at: datetime | None = None

    # Execution
    execution_attempts: int = 0
    max_retries: int = 3
    retry_delay_seconds: int = 5

    # Results
    result_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    # Compensation (saga)
    compensation_steps: list[dict[str, Any]] = field(default_factory=list)

    # Audit trail
    transitions: list[dict[str, Any]] = field(default_factory=list)

    def transition_to(self, new_state: WriteActionState, reason: str = ""):
        """Record state transition."""
        self.transitions.append({
            "from": self.state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.state = new_state
        log.info(
            "write_action_transition",
            action_id=self.input.action_id,
            from_state=self.transitions[-1]["from"],
            to_state=new_state.value,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "input": self.input.to_dict(),
            "state": self.state.value,
            "execution_id": self.execution_id,
            "policy_approved": self.policy_approved,
            "policy_reason": self.policy_reason,
            "policy_guardrails_triggered": self.policy_guardrails_triggered,
            "approval_required": self.approval_required,
            "approval_actor_id": self.approval_actor_id,
            "approval_decision": self.approval_decision,
            "approval_timestamp": self.approval_timestamp.isoformat() if self.approval_timestamp else None,
            "approval_expires_at": self.approval_expires_at.isoformat() if self.approval_expires_at else None,
            "execution_attempts": self.execution_attempts,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "compensation_steps": self.compensation_steps,
            "transitions": self.transitions,
        }


@dataclass
class WriteActionResult:
    """Result of write action workflow."""

    action_id: str
    success: bool
    state: WriteActionState
    result_data: dict[str, Any]
    error_message: str | None = None
    compensation_performed: bool = False
    audit_trail: list[dict[str, Any]] = field(default_factory=list)


class WriteActionActivity(ABC):
    """Base class for write action activities (to be executed by tools)."""

    @abstractmethod
    async def execute(self, context: WriteActionContext) -> dict[str, Any]:
        """Execute the activity.

        Args:
            context: Write action context

        Returns:
            Dictionary with execution result
        """

    @abstractmethod
    async def compensate(self, context: WriteActionContext) -> dict[str, Any]:
        """Compensate (rollback) the activity.

        Args:
            context: Write action context

        Returns:
            Dictionary with compensation result
        """


class WriteActionWorkflow:
    """Orchestrator for write action 8-state machine."""

    def __init__(self, policy_engine, approval_service, tool_executor):
        """Initialize workflow.

        Args:
            policy_engine: OPA policy engine
            approval_service: Approval service for L2/L3 decisions
            tool_executor: Tool executor for running actual operations
        """
        self.policy_engine = policy_engine
        self.approval_service = approval_service
        self.tool_executor = tool_executor

    async def execute(self, action_input: WriteActionInput) -> WriteActionResult:
        """Execute write action through full state machine.

        Args:
            action_input: Write action input

        Returns:
            WriteActionResult
        """
        context = WriteActionContext(input=action_input, state=WriteActionState.PROPOSED)

        try:
            # State 1: PROPOSED -> POLICY_REVIEW
            await self._transition_to_policy_review(context)

            # State 2: POLICY_REVIEW
            await self._execute_policy_review(context)

            # State 3: Check if approval needed, transition accordingly
            if context.approval_required:
                await self._transition_to_approval_pending(context)
                # State 3: APPROVAL_PENDING
                await self._wait_for_approval(context)

            # State 4: EXECUTING
            if context.policy_approved:
                await self._transition_to_executing(context)
                await self._execute_action(context)

            # State 5-6: Result handling
            if context.error_message and context.execution_attempts < context.max_retries:
                await self._transition_to_retrying(context)
                await self._retry_action(context)

            # Final state: SUCCEEDED or FAILED
            if context.error_message:
                context.transition_to(WriteActionState.FAILED, f"Failed after {context.execution_attempts} attempts")
            else:
                context.transition_to(WriteActionState.SUCCEEDED, "Action completed successfully")

        except Exception as e:
            log.error("write_action_workflow_error", action_id=context.input.action_id, error=str(e))
            context.error_message = str(e)
            context.transition_to(WriteActionState.FAILED, f"Workflow error: {e!s}")

            # State 7: COMPENSATING (on failure)
            await self._compensate(context)

        return WriteActionResult(
            action_id=context.input.action_id,
            success=context.state == WriteActionState.SUCCEEDED,
            state=context.state,
            result_data=context.result_data,
            error_message=context.error_message,
            compensation_performed=len(context.compensation_steps) > 0,
            audit_trail=context.transitions,
        )

    async def _transition_to_policy_review(self, context: WriteActionContext) -> None:
        """Transition PROPOSED -> POLICY_REVIEW."""
        context.transition_to(WriteActionState.POLICY_REVIEW, "Moving to policy evaluation")

    async def _execute_policy_review(self, context: WriteActionContext) -> None:
        """Execute policy review using OPA."""
        log.info("policy_review_starting", action_id=context.input.action_id, action_type=context.input.action_type)

        try:
            policy_result = await self.policy_engine.evaluate(
                action_type=context.input.action_type,
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                arguments=context.input.arguments,
                context=context.input.context,
            )

            context.policy_approved = policy_result.get("approved", False)
            context.policy_reason = policy_result.get("reason", "")
            context.policy_guardrails_triggered = policy_result.get("guardrails_triggered", [])

            # Check if approval is required
            context.approval_required = policy_result.get("approval_required", False)

            log.info(
                "policy_review_complete",
                action_id=context.input.action_id,
                approved=context.policy_approved,
                approval_required=context.approval_required,
            )
        except Exception as e:
            log.error("policy_review_error", action_id=context.input.action_id, error=str(e))
            context.policy_approved = False
            context.policy_reason = f"Policy review error: {e!s}"

    async def _transition_to_approval_pending(self, context: WriteActionContext) -> None:
        """Transition POLICY_REVIEW -> APPROVAL_PENDING."""
        context.transition_to(WriteActionState.APPROVAL_PENDING, "Awaiting human approval")
        context.approval_expires_at = datetime.utcnow() + timedelta(hours=4)

    async def _wait_for_approval(self, context: WriteActionContext) -> None:
        """Wait for human approval (max 4 hours, auto-escalate after)."""
        log.info("approval_requested", action_id=context.input.action_id, expires_at=context.approval_expires_at)

        try:
            # Create approval request in approval service
            approval_request = await self.approval_service.create_request(
                action_id=context.input.action_id,
                tenant_id=context.input.tenant_id,
                action_type=context.input.action_type,
                arguments=context.input.arguments,
                context=context.input.context,
                expires_at=context.approval_expires_at,
            )

            # Wait for approval (simulated; in real Temporal, this would use signals/conditions)
            approval_decision = await self.approval_service.wait_for_decision(
                approval_request_id=approval_request["id"],
                timeout_seconds=14400,  # 4 hours
            )

            context.approval_decision = approval_decision.get("approved", False)
            context.approval_actor_id = approval_decision.get("actor_id")
            context.approval_timestamp = datetime.fromisoformat(approval_decision.get("timestamp", datetime.utcnow().isoformat()))

            if not context.approval_decision:
                context.policy_approved = False
                context.policy_reason = f"Approval denied by {context.approval_actor_id}"

        except TimeoutError:
            log.warning("approval_timeout", action_id=context.input.action_id)
            # Auto-escalate after 4h
            context.policy_approved = False
            context.policy_reason = "Approval timeout - auto-escalated after 4 hours"

    async def _transition_to_executing(self, context: WriteActionContext) -> None:
        """Transition to EXECUTING state."""
        context.transition_to(WriteActionState.EXECUTING, "Starting action execution")

    async def _execute_action(self, context: WriteActionContext) -> None:
        """Execute the write action."""
        context.execution_attempts += 1
        log.info(
            "write_action_executing",
            action_id=context.input.action_id,
            action_type=context.input.action_type,
            attempt=context.execution_attempts,
        )

        try:
            # Route to appropriate tool based on action_type
            tool_result = await self._route_to_tool(context)

            context.result_data = tool_result
            context.error_message = None

        except Exception as e:
            log.error("write_action_execution_error", action_id=context.input.action_id, error=str(e))
            context.error_message = str(e)
            # Record compensation step for later rollback
            context.compensation_steps.append({
                "action_type": context.input.action_type.value,
                "attempted_args": context.input.arguments,
            })

    async def _route_to_tool(self, context: WriteActionContext) -> dict[str, Any]:
        """Route action to appropriate tool executor."""
        action_type = context.input.action_type

        if action_type == WriteActionType.REFUND:
            return await self.tool_executor.execute_refund(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        elif action_type == WriteActionType.RETURN_RMA:
            return await self.tool_executor.execute_return_rma(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        elif action_type == WriteActionType.CANCEL_ORDER:
            return await self.tool_executor.execute_cancel_order(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        elif action_type == WriteActionType.ADDRESS_CHANGE:
            return await self.tool_executor.execute_address_change(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        elif action_type == WriteActionType.PASSWORD_RESET:
            return await self.tool_executor.execute_password_reset(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        elif action_type == WriteActionType.PLAN_CHANGE:
            return await self.tool_executor.execute_plan_change(
                tenant_id=context.input.tenant_id,
                customer_id=context.input.customer_id,
                **context.input.arguments,
            )
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def _transition_to_retrying(self, context: WriteActionContext) -> None:
        """Transition to RETRYING state."""
        context.transition_to(
            WriteActionState.RETRYING,
            f"Retrying after error (attempt {context.execution_attempts})",
        )

    async def _retry_action(self, context: WriteActionContext) -> None:
        """Retry the action."""
        await asyncio.sleep(context.retry_delay_seconds * context.execution_attempts)  # Exponential backoff
        await self._execute_action(context)

    async def _compensate(self, context: WriteActionContext) -> None:
        """Compensate (rollback) the action (Saga compensation)."""
        if context.state not in (WriteActionState.FAILED, WriteActionState.EXECUTING, WriteActionState.RETRYING):
            return  # Nothing to compensate

        context.transition_to(WriteActionState.COMPENSATING, "Rolling back failed action")

        log.info("saga_compensation_starting", action_id=context.input.action_id, compensation_steps=len(context.compensation_steps))

        # Reverse order of compensation
        for step in reversed(context.compensation_steps):
            try:
                await self._execute_compensation_step(context, step)
            except Exception as e:
                log.error("compensation_step_error", action_id=context.input.action_id, step=step, error=str(e))

    async def _execute_compensation_step(self, context: WriteActionContext, step: dict[str, Any]) -> None:
        """Execute a single compensation step."""
        action_type_str = step.get("action_type")

        # Map action types to their compensation logic
        if action_type_str == WriteActionType.REFUND.value:
            # Reverse a refund: re-charge customer (or flag for manual review)
            log.info("compensating_refund", action_id=context.input.action_id)
        elif action_type_str == WriteActionType.CANCEL_ORDER.value:
            # Reverse a cancellation: restore order
            log.info("compensating_cancel", action_id=context.input.action_id)
        else:
            log.warning("no_compensation_logic", action_type=action_type_str)
