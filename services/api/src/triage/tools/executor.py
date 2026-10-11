"""Tool execution with autonomy gating and idempotency."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional
import structlog

from triage.models.decision import AutonomyLevel
from triage.tools.registry import ToolSpec

log = structlog.get_logger()


@dataclass
class ToolExecutionResult:
    """Result of tool execution."""

    tool_name: str
    success: bool
    execution_id: str
    result_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ToolExecutor:
    """Execute tools with autonomy gating and idempotency."""

    def __init__(self, autonomy_level: AutonomyLevel, tenant_id: str, customer_id: str):
        """Initialize executor.

        Args:
            autonomy_level: Current autonomy level
            tenant_id: Current tenant ID
            customer_id: Current customer ID
        """
        self.autonomy_level = autonomy_level
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.execution_cache: Dict[str, ToolExecutionResult] = {}  # Idempotency cache

    def execute(
        self,
        tool_spec: ToolSpec,
        args: Dict[str, Any],
        message_id: str,
    ) -> ToolExecutionResult:
        """Execute a tool with autonomy gating and idempotency.

        Args:
            tool_spec: Tool specification
            args: Bound arguments
            message_id: Message ID (for audit trail)

        Returns:
            ToolExecutionResult
        """
        # Check 1: Autonomy level gating
        if self.autonomy_level < tool_spec.min_autonomy_level:
            log.warning(
                "tool_execution_blocked_autonomy",
                tool=tool_spec.name,
                current_level=self.autonomy_level,
                required_level=tool_spec.min_autonomy_level,
            )
            return ToolExecutionResult(
                tool_name=tool_spec.name,
                success=False,
                execution_id=str(uuid.uuid4()),
                error=f"Autonomy level {self.autonomy_level} insufficient for {tool_spec.name}",
            )

        # Check 2: Idempotency
        idempotency_key = self._generate_idempotency_key(tool_spec, args, message_id)

        if idempotency_key in self.execution_cache:
            cached_result = self.execution_cache[idempotency_key]
            log.info(
                "tool_execution_cached",
                tool=tool_spec.name,
                idempotency_key=idempotency_key,
            )
            return cached_result

        # Execute tool (mock for now)
        try:
            result_data = self._execute_tool_impl(tool_spec, args)

            execution_result = ToolExecutionResult(
                tool_name=tool_spec.name,
                success=True,
                execution_id=str(uuid.uuid4()),
                result_data=result_data,
            )

            # Cache result
            self.execution_cache[idempotency_key] = execution_result

            log.info(
                "tool_execution_success",
                tool=tool_spec.name,
                tenant_id=self.tenant_id,
                customer_id=self.customer_id,
            )

            return execution_result

        except Exception as e:
            log.error(
                "tool_execution_error",
                tool=tool_spec.name,
                error=str(e),
            )
            return ToolExecutionResult(
                tool_name=tool_spec.name,
                success=False,
                execution_id=str(uuid.uuid4()),
                error=str(e),
            )

    @staticmethod
    def _generate_idempotency_key(
        tool_spec: ToolSpec,
        args: Dict[str, Any],
        message_id: str,
    ) -> str:
        """Generate idempotency key to prevent duplicate executions.

        Args:
            tool_spec: Tool specification
            args: Bound arguments
            message_id: Message ID

        Returns:
            Idempotency key
        """
        # Use tool name + key argument + message ID
        key_field = tool_spec.idempotency_key_field or "message_id"
        key_value = args.get(key_field, message_id)

        key_text = f"{tool_spec.name}:{key_value}:{message_id}"
        return hashlib.sha256(key_text.encode()).hexdigest()

    @staticmethod
    def _execute_tool_impl(tool_spec: ToolSpec, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool (mock implementation).

        Args:
            tool_spec: Tool specification
            args: Bound arguments

        Returns:
            Result data

        Raises:
            Exception: If tool execution fails
        """
        # In production: call external API, database, etc.
        # For now: mock implementation
        return {
            "tool": tool_spec.name,
            "status": "executed",
            "args": args,
        }
