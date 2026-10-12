"""Sandbox tenant for demo and testing (S10.9)."""

import copy
from dataclasses import dataclass, field
from typing import Any

SANDBOX_TENANT_ID = "sandbox_demo_12345"


@dataclass
class SandboxConversation:
    """Sample conversation for sandbox."""

    id: str
    customer_name: str
    message: str
    intent: str
    status: str


@dataclass
class SandboxKnowledgeBase:
    """Sample KB entries for sandbox."""

    entries: list[dict[str, str]] = field(default_factory=list)


class SandboxTenant:
    """Sandbox tenant with pre-loaded demo data and dry-run mode."""

    def __init__(self):
        self.tenant_id = SANDBOX_TENANT_ID
        self.conversations: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.kb_entries: list[dict[str, Any]] = []
        self.initial_state = None
        self._initialize_sandbox()

    def _initialize_sandbox(self):
        """Initialize sandbox with seeded data."""
        # 5 sample conversations
        self.conversations = [
            {
                "id": "conv_sandbox_001",
                "customer_id": "cust_sandbox_alice",
                "customer_name": "Alice Johnson",
                "channel_id": "email",
                "status": "resolved",
                "intent_primary": "billing",
                "created_at": "2026-01-10T10:00:00Z",
            },
            {
                "id": "conv_sandbox_002",
                "customer_id": "cust_sandbox_bob",
                "customer_name": "Bob Smith",
                "channel_id": "chat",
                "status": "open",
                "intent_primary": "account_access",
                "created_at": "2026-01-11T14:30:00Z",
            },
            {
                "id": "conv_sandbox_003",
                "customer_id": "cust_sandbox_carol",
                "customer_name": "Carol Davis",
                "channel_id": "phone",
                "status": "escalated",
                "intent_primary": "technical_issue",
                "created_at": "2026-01-11T16:00:00Z",
            },
            {
                "id": "conv_sandbox_004",
                "customer_id": "cust_sandbox_david",
                "customer_name": "David Wilson",
                "channel_id": "email",
                "status": "resolved",
                "intent_primary": "billing",
                "created_at": "2026-01-09T09:00:00Z",
            },
            {
                "id": "conv_sandbox_005",
                "customer_id": "cust_sandbox_eve",
                "customer_name": "Eve Martinez",
                "channel_id": "chat",
                "status": "pending",
                "intent_primary": "feature_request",
                "created_at": "2026-01-11T20:00:00Z",
            },
        ]

        # 20 sample messages (4 + 4 + 4 + 4 + 4)
        self.messages = [
            # Conversation 001
            {"id": f"msg_001_{i}", "conversation_id": "conv_sandbox_001",
             "sender": "customer", "body": f"Question {i} about billing"}
            for i in range(1, 5)
        ] + [
            # Conversation 002
            {"id": f"msg_002_{i}", "conversation_id": "conv_sandbox_002",
             "sender": "customer", "body": f"Help with account {i}"}
            for i in range(1, 5)
        ] + [
            # Conversation 003
            {"id": f"msg_003_{i}", "conversation_id": "conv_sandbox_003",
             "sender": "customer", "body": f"Technical problem {i}"}
            for i in range(1, 5)
        ] + [
            # Conversation 004
            {"id": f"msg_004_{i}", "conversation_id": "conv_sandbox_004",
             "sender": "customer", "body": f"Billing inquiry {i}"}
            for i in range(1, 5)
        ] + [
            # Conversation 005
            {"id": f"msg_005_{i}", "conversation_id": "conv_sandbox_005",
             "sender": "customer", "body": f"Feature suggestion {i}"}
            for i in range(1, 5)
        ]

        # Pre-loaded KB
        self.kb_entries = [
            {
                "id": "kb_001",
                "title": "How to reset password",
                "content": "To reset your password: 1) Click forgot password 2) Enter email 3) Check inbox for link",
                "intent": "account_access",
            },
            {
                "id": "kb_002",
                "title": "Billing FAQs",
                "content": "Common billing questions and answers for monthly/annual plans.",
                "intent": "billing",
            },
            {
                "id": "kb_003",
                "title": "Getting started guide",
                "content": "Step-by-step guide to set up your account and first workflows.",
                "intent": "onboarding",
            },
            {
                "id": "kb_004",
                "title": "API documentation",
                "content": "Complete API reference with examples and SDKs.",
                "intent": "technical_issue",
            },
            {
                "id": "kb_005",
                "title": "Feature roadmap",
                "content": "Planned features and enhancements for the next 6 months.",
                "intent": "feature_request",
            },
        ]

        # Save initial state for reset
        self.initial_state = {
            "conversations": copy.deepcopy(self.conversations),
            "messages": copy.deepcopy(self.messages),
            "kb_entries": copy.deepcopy(self.kb_entries),
        }

    async def dry_run_write(
        self,
        operation: str,
        provider: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Execute write operation in dry-run mode (doesn't hit external services).

        Args:
            operation: Operation name (charge, fulfill_order, etc.)
            provider: Provider name (stripe, shopify, etc.)
            **kwargs: Operation parameters

        Returns:
            Mock success response
        """
        # Simulate operations without hitting actual providers
        if provider == "stripe":
            return {
                "success": True,
                "provider": "stripe",
                "operation": operation,
                "dry_run": True,
                "message": f"Would {operation} via Stripe (not actually charged)",
                "mock_response": {
                    "id": f"mock_{operation}_123",
                    "status": "success",
                },
            }
        elif provider == "shopify":
            return {
                "success": True,
                "provider": "shopify",
                "operation": operation,
                "dry_run": True,
                "message": f"Would {operation} via Shopify (not actually fulfilled)",
                "mock_response": {
                    "id": f"mock_{operation}_456",
                    "status": "pending",
                },
            }
        else:
            return {
                "success": True,
                "provider": provider,
                "operation": operation,
                "dry_run": True,
                "message": f"Dry-run {operation}",
            }

    async def reset_to_initial_state(self) -> bool:
        """Reset sandbox to initial state (admin operation).

        Returns:
            True if successful
        """
        if not self.initial_state:
            return False

        self.conversations = copy.deepcopy(self.initial_state["conversations"])
        self.messages = copy.deepcopy(self.initial_state["messages"])
        self.kb_entries = copy.deepcopy(self.initial_state["kb_entries"])

        return True

    def get_sample_conversations(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get sample conversations."""
        return self.conversations[:limit]

    def get_sample_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get sample messages for conversation."""
        return [m for m in self.messages if m["conversation_id"] == conversation_id]

    def get_kb(self) -> list[dict[str, Any]]:
        """Get sample knowledge base."""
        return self.kb_entries

    def verify_initialization(self) -> bool:
        """Verify sandbox initialized correctly."""
        return (
            len(self.conversations) == 5
            and len(self.messages) == 20
            and len(self.kb_entries) == 5
        )


# Singleton instance
_sandbox_instance: SandboxTenant | None = None


def get_sandbox_tenant() -> SandboxTenant:
    """Get or create sandbox tenant instance."""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = SandboxTenant()
    return _sandbox_instance


def is_sandbox_tenant(tenant_id: str) -> bool:
    """Check if tenant ID is sandbox."""
    return tenant_id == SANDBOX_TENANT_ID
