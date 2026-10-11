"""Prompt building with token budget enforcement."""

from typing import List, Optional
import structlog

log = structlog.get_logger()


class PromptBuilder:
    """Build prompts with token budget enforcement."""

    def __init__(self, token_budget: int = 4000):
        """Initialize prompt builder.

        Args:
            token_budget: Maximum tokens for full prompt
        """
        self.token_budget = token_budget
        self.system_prompt_tokens = 200  # Reserve for system prompt

    def build(
        self,
        system_prompt: str,
        user_message: str,
        entities: Optional[List[str]] = None,
        intents: Optional[List[str]] = None,
        customer_tier: Optional[str] = None,
        retrieved_docs: Optional[List[str]] = None,
    ) -> tuple[str, int]:
        """Build full prompt within token budget.

        Args:
            system_prompt: System instructions
            user_message: User's message
            entities: List of extracted entities
            intents: List of classified intents
            customer_tier: Customer tier (premium, standard, etc.)
            retrieved_docs: Retrieved context documents

        Returns:
            (full_prompt, token_count)
        """
        parts = [system_prompt]
        tokens_used = self._estimate_tokens(system_prompt)

        # Add entity context (minimal)
        if entities:
            entity_section = "EXTRACTED ENTITIES:\n" + "\n".join(f"- {e}" for e in entities)
            entity_tokens = self._estimate_tokens(entity_section)
            if tokens_used + entity_tokens < self.token_budget:
                parts.append(entity_section)
                tokens_used += entity_tokens

        # Add intent context
        if intents:
            intent_section = "DETECTED INTENTS:\n" + ", ".join(intents)
            intent_tokens = self._estimate_tokens(intent_section)
            if tokens_used + intent_tokens < self.token_budget:
                parts.append(intent_section)
                tokens_used += intent_tokens

        # Add customer tier
        if customer_tier:
            tier_section = f"CUSTOMER TIER: {customer_tier}"
            tier_tokens = self._estimate_tokens(tier_section)
            if tokens_used + tier_tokens < self.token_budget:
                parts.append(tier_section)
                tokens_used += tier_tokens

        # Add retrieved documents (most important)
        if retrieved_docs:
            # Budget for retrieved docs
            available_for_docs = self.token_budget - tokens_used - 200  # Reserve 200 for user message
            doc_text = self._build_doc_section(retrieved_docs, available_for_docs)
            if doc_text:
                parts.append(doc_text)
                tokens_used += self._estimate_tokens(doc_text)

        # Add user message (always include)
        user_section = f"USER MESSAGE:\n{user_message}"
        parts.append(user_section)
        tokens_used += self._estimate_tokens(user_section)

        full_prompt = "\n\n".join(parts)

        log.debug(
            "prompt_built",
            token_count=tokens_used,
            budget=self.token_budget,
            sections=len(parts),
        )

        return full_prompt, tokens_used

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (simple word-based heuristic).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        words = text.split()
        return int(len(words) * 1.3)  # 1 token ≈ 0.77 words

    @staticmethod
    def _build_doc_section(docs: List[str], available_tokens: int) -> str:
        """Build retrieved documents section within token budget.

        Args:
            docs: List of document texts
            available_tokens: Maximum tokens for this section

        Returns:
            Section text or empty if doesn't fit
        """
        parts = ["RETRIEVED CONTEXT:"]
        tokens_used = PromptBuilder._estimate_tokens(parts[0])

        for i, doc in enumerate(docs):
            # Truncate long documents
            if len(doc) > 500:
                doc = doc[:500] + "..."

            doc_line = f"\n{i + 1}. {doc}"
            doc_tokens = PromptBuilder._estimate_tokens(doc_line)

            if tokens_used + doc_tokens < available_tokens:
                parts.append(doc_line)
                tokens_used += doc_tokens
            else:
                # Stop adding docs if budget exceeded
                break

        if len(parts) > 1:
            return "".join(parts)
        return ""
