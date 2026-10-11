"""Response generation using LiteLLM and Claude."""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional
import structlog

log = structlog.get_logger()


@dataclass
class GenerationResult:
    """Result of LLM generation."""

    response_text: str
    model: str
    tokens_used: int
    latency_ms: float
    error: Optional[str] = None


class ResponseGenerator:
    """Generate responses using LLM via LiteLLM abstraction."""

    def __init__(self, model: Optional[str] = None):
        """Initialize generator.

        Args:
            model: Model name (default from CLAUDE_MODEL env var)
        """
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")
        self.max_retries = 3
        self.base_retry_delay = 1.0  # seconds
        self._init_litellm()

    def _init_litellm(self):
        """Initialize LiteLLM client."""
        try:
            import litellm
            self.litellm = litellm
            log.info("litellm_initialized", model=self.model)
        except ImportError:
            log.warning("litellm_not_available")
            self.litellm = None

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: str = "",
        max_tokens: int = 1000,
    ) -> GenerationResult:
        """Generate response using LLM.

        Args:
            system_prompt: System prompt for LLM
            user_message: User's message
            context: Additional context (retrieved docs, entities, etc.)
            max_tokens: Maximum tokens in response

        Returns:
            GenerationResult with response text and metadata
        """
        start_time = time.perf_counter()

        # Build full prompt
        full_prompt = self._build_full_prompt(system_prompt, context, user_message)

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                result = await self._call_llm(full_prompt, max_tokens)
                latency_ms = (time.perf_counter() - start_time) * 1000

                log.info(
                    "generation_success",
                    model=self.model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    tokens=result.tokens_used,
                )

                return GenerationResult(
                    response_text=result.response_text,
                    model=self.model,
                    tokens_used=result.tokens_used,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_retry_delay * (2**attempt)
                    log.warning(
                        "generation_retry",
                        attempt=attempt,
                        delay_sec=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    log.error("generation_failed", attempts=self.max_retries, error=str(e))
                    return GenerationResult(
                        response_text="",
                        model=self.model,
                        tokens_used=0,
                        latency_ms=latency_ms,
                        error=str(e),
                    )

        return GenerationResult(
            response_text="",
            model=self.model,
            tokens_used=0,
            latency_ms=(time.perf_counter() - start_time) * 1000,
            error="Max retries exceeded",
        )

    async def _call_llm(self, prompt: str, max_tokens: int) -> "GenerationResult":
        """Call LLM via LiteLLM.

        Args:
            prompt: Full prompt
            max_tokens: Max tokens in response

        Returns:
            GenerationResult
        """
        if not self.litellm:
            raise RuntimeError("LiteLLM not available")

        # Mock implementation for testing
        # In production: use litellm.completion() or litellm.acompletion()
        response_text = f"[Generated response for: {prompt[:50]}...]"
        tokens_used = len(prompt.split()) + len(response_text.split())

        return GenerationResult(
            response_text=response_text,
            model=self.model,
            tokens_used=tokens_used,
            latency_ms=0,
        )

    @staticmethod
    def _build_full_prompt(system_prompt: str, context: str, user_message: str) -> str:
        """Build full prompt with system, context, and user message.

        Args:
            system_prompt: System instructions
            context: Context (entities, retrieved docs, etc.)
            user_message: User's message

        Returns:
            Full prompt
        """
        parts = [system_prompt]

        if context.strip():
            parts.append("CONTEXT:")
            parts.append(context)

        parts.append("USER MESSAGE:")
        parts.append(user_message)

        return "\n\n".join(parts)
