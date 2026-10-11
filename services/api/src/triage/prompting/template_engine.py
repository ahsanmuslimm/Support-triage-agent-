"""S3.7: Prompt Template Engine with Jinja2."""

import logging
from typing import Dict, Any, Optional
from jinja2 import Environment, BaseLoader, TemplateError

logger = logging.getLogger(__name__)


class PromptTemplateEngine:
    """Jinja2-based dynamic prompt templates with token budget enforcement."""

    def __init__(self, max_tokens: int = 3500):
        self.max_tokens = max_tokens
        self.jinja_env = Environment(loader=BaseLoader())
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, str]:
        """Load Jinja2 prompt templates with conditional blocks."""
        return {
            "default": """You are a helpful customer support agent.

Customer: {{ customer_name }}
{% if account_age_days %}Account Age: {{ account_age_days }} days{% endif %}
{% if order_count %}Order History: {{ order_count }} orders, ${{ "%.2f"|format(total_spent) }} total{% endif %}

{% if reasoning %}{{ reasoning }}{% endif %}

Please respond helpfully and professionally.""",
            "empathy": """You are a compassionate customer support agent helping a valued customer who may be experiencing challenges.

Customer: {{ customer_name }}
Status: We care about your experience and want to help
{% if account_age_days %}Account Age: {{ account_age_days }} days{% endif %}

{% if reasoning %}{{ reasoning }}{% endif %}

Please respond with genuine empathy and understanding. Your satisfaction is important to us. We're here to help resolve your issue.""",
            "urgency": """You are a priority support agent assisting a valued customer.

Customer: {{ customer_name }}
VIP Status: Priority Customer
{% if order_count %}Order History: {{ order_count }} orders, ${{ "%.2f"|format(total_spent) }} total{% endif %}

{% if reasoning %}{{ reasoning }}{% endif %}

Please prioritize this request and offer our best support options. This customer's satisfaction is critical.""",
            "formal": """You are an enterprise support specialist providing professional assistance.

Account: {{ customer_name }}
Support Level: Enterprise
{% if account_age_days %}Account Age: {{ account_age_days }} days{% endif %}

{% if reasoning %}{{ reasoning }}{% endif %}

Please provide formal, detailed, and professional support with full documentation. Ensure all procedures are followed to enterprise standards.""",
        }

    def _truncate_context_for_budget(
        self,
        text: str,
        max_chars: int,
    ) -> str:
        """Truncate context while preserving structure."""
        if len(text) <= max_chars:
            return text
        
        logger.warning(f"Prompt exceeds budget ({len(text)} chars > {max_chars}), truncating")
        # Truncate with ellipsis, preserving sentence boundaries where possible
        truncated = text[:max_chars - 3].rsplit('\n', 1)[0]
        return truncated + "..."

    def render(
        self,
        tone: str,
        customer_context: Dict[str, Any],
        reasoning: str = "",
    ) -> str:
        """
        Render prompt template with context using Jinja2.

        Args:
            tone: 'default', 'empathy', 'urgency', 'formal'
            customer_context: Customer data dict
            reasoning: Decision reasoning/context

        Returns:
            Rendered prompt string (respects token budget)
        """
        template_str = self.templates.get(tone, self.templates["default"])

        try:
            # Create Jinja2 template
            template = self.jinja_env.from_string(template_str)

            # Prepare context with safe defaults
            context = {
                "customer_name": customer_context.get("name", "Valued Customer"),
                "account_age_days": customer_context.get("account_age_days"),
                "order_count": customer_context.get("order_count"),
                "total_spent": customer_context.get("total_spent", 0),
                "reasoning": reasoning,
            }

            # Render template
            prompt = template.render(**context)

            # Enforce token budget (4 chars ≈ 1 token)
            max_chars = self.max_tokens * 4
            if len(prompt) > max_chars:
                prompt = self._truncate_context_for_budget(prompt, max_chars)

            return prompt

        except TemplateError as e:
            logger.error(f"Template rendering error: {e}")
            # Fallback to simple rendering
            return self._fallback_render(tone, customer_context, reasoning)

    def _fallback_render(
        self,
        tone: str,
        customer_context: Dict[str, Any],
        reasoning: str,
    ) -> str:
        """Fallback simple rendering if Jinja2 fails."""
        fallback_templates = {
            "default": f"You are a helpful support agent. Customer: {customer_context.get('name', 'Customer')}. {reasoning}",
            "empathy": f"You are a compassionate support agent. We care about {customer_context.get('name', 'this customer')}. {reasoning}",
            "urgency": f"You are a priority support agent. {customer_context.get('name', 'This customer')} is important. {reasoning}",
            "formal": f"You are a professional support specialist. {reasoning}",
        }
        return fallback_templates.get(tone, fallback_templates["default"])

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (1 token ≈ 4 characters)."""
        return len(text) // 4

    def get_token_budget_info(self) -> Dict[str, Any]:
        """Return token budget configuration."""
        return {
            "max_tokens": self.max_tokens,
            "max_chars": self.max_tokens * 4,
            "estimation_method": "1 token ≈ 4 characters",
        }
