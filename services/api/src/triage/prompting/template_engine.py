"""S3.7: Prompt Template Engine."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PromptTemplateEngine:
    """Jinja2-based dynamic prompt templates with token budget enforcement."""

    def __init__(self, max_tokens: int = 3500):
        self.max_tokens = max_tokens
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, str]:
        """Load prompt templates (simplified for now)."""
        return {
            "default": """You are a helpful customer support agent.

Customer: {customer_name}
Account Age: {account_age_days} days
Order History: {order_count} orders, ${total_spent:.2f} total

{reasoning}

Please respond helpfully and professionally.""",
            "empathy": """You are a compassionate customer support agent helping a valued customer who may be experiencing churn risk.

Customer: {customer_name}
Status: At Risk - Please provide extra empathy and care

{reasoning}

Please respond with genuine care and understanding. We want to help resolve their issue.""",
            "urgency": """You are a priority support agent assisting a high-value customer.

Customer: {customer_name}
VIP Status: Valued Customer
Order History: {order_count} orders, ${total_spent:.2f} total

{reasoning}

Please prioritize resolution and offer premium support options.""",
            "formal": """You are an enterprise support specialist.

Account: {customer_name}
Enterprise Status: Active

{reasoning}

Please provide formal, detailed, and professional support appropriate for enterprise accounts.""",
        }

    def render(
        self,
        tone: str,
        customer_context: Dict[str, Any],
        reasoning: str = "",
    ) -> str:
        """
        Render prompt template with context.

        Args:
            tone: 'default', 'empathy', 'urgency', 'formal'
            customer_context: Customer data dict
            reasoning: Decision reasoning/context

        Returns:
            Rendered prompt string
        """
        template = self.templates.get(tone, self.templates["default"])

        # Prepare context
        context = {
            "customer_name": customer_context.get("name", "Valued Customer"),
            "account_age_days": customer_context.get("account_age_days", 0),
            "order_count": customer_context.get("order_count", 0),
            "total_spent": customer_context.get("total_spent", 0),
            "reasoning": reasoning,
        }

        # Simple template substitution (not Jinja2 for now)
        prompt = template.format(**context)

        # Enforce token budget (rough estimate: 1 token ≈ 4 characters)
        if len(prompt) > self.max_tokens * 4:
            logger.warning(f"Prompt exceeds token budget, truncating")
            prompt = prompt[: self.max_tokens * 4]

        return prompt

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate (1 token ≈ 4 characters)."""
        return len(text) // 4
