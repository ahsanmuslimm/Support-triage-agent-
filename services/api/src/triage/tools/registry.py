"""Tool registry: register and lookup available tools."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
import structlog

log = structlog.get_logger()


class AutonomyLevel(int, Enum):
    """Autonomy levels required for tools."""

    L0_READ_ONLY = 0
    L1_SUGGEST = 1
    L2_CONFIRM = 2
    L3_AUTO = 3


@dataclass
class ToolSpec:
    """Specification for a single tool."""

    name: str
    description: str
    required_args: Dict[str, str]  # arg_name -> arg_type
    min_autonomy_level: AutonomyLevel
    idempotency_key_field: Optional[str] = None  # Field used for idempotency
    is_destructive: bool = False


class ToolRegistry:
    """Registry of available tools."""

    # Built-in tools
    BUILTIN_TOOLS = {
        "send_email": ToolSpec(
            name="send_email",
            description="Send email to customer",
            required_args={"to": "string", "subject": "string", "body": "string"},
            min_autonomy_level=AutonomyLevel.L1_SUGGEST,
        ),
        "create_ticket": ToolSpec(
            name="create_ticket",
            description="Create support ticket",
            required_args={"title": "string", "description": "string", "priority": "string"},
            min_autonomy_level=AutonomyLevel.L1_SUGGEST,
        ),
        "lookup_order": ToolSpec(
            name="lookup_order",
            description="Look up order details",
            required_args={"order_id": "string"},
            min_autonomy_level=AutonomyLevel.L0_READ_ONLY,
        ),
        "issue_refund": ToolSpec(
            name="issue_refund",
            description="Issue refund to customer",
            required_args={"order_id": "string", "amount": "float"},
            min_autonomy_level=AutonomyLevel.L2_CONFIRM,
            is_destructive=True,
            idempotency_key_field="order_id",
        ),
        "reset_password": ToolSpec(
            name="reset_password",
            description="Send password reset email",
            required_args={"account_id": "string", "email": "string"},
            min_autonomy_level=AutonomyLevel.L1_SUGGEST,
        ),
        "cancel_order": ToolSpec(
            name="cancel_order",
            description="Cancel customer order",
            required_args={"order_id": "string"},
            min_autonomy_level=AutonomyLevel.L2_CONFIRM,
            is_destructive=True,
        ),
    }

    def __init__(self):
        """Initialize registry with built-in tools."""
        self.tools: Dict[str, ToolSpec] = self.BUILTIN_TOOLS.copy()
        log.info("tool_registry_initialized", tool_count=len(self.tools))

    def register(self, spec: ToolSpec) -> None:
        """Register a new tool.

        Args:
            spec: ToolSpec for the tool
        """
        self.tools[spec.name] = spec
        log.info("tool_registered", tool_name=spec.name)

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Get tool by name.

        Args:
            name: Tool name

        Returns:
            ToolSpec or None if not found
        """
        return self.tools.get(name)

    def list_tools(self) -> Dict[str, ToolSpec]:
        """Get all registered tools.

        Returns:
            Dict of tool_name -> ToolSpec
        """
        return self.tools.copy()

    def get_tools_for_autonomy_level(self, level: AutonomyLevel) -> Dict[str, ToolSpec]:
        """Get all tools available at given autonomy level.

        Args:
            level: Autonomy level

        Returns:
            Dict of available tools
        """
        return {
            name: spec
            for name, spec in self.tools.items()
            if spec.min_autonomy_level <= level
        }
