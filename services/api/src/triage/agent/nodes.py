"""LangGraph nodes for triage agent."""

import structlog
from typing import Any

from triage.models.triage_state import TriageState
from triage.models.decision import AutonomyLevel
from triage.classification.classifier import IntentClassifier
from triage.entity.extractor import RuleBasedEntityExtractor
from triage.decision.matrix import DecisionMatrix
from triage.retrieval.hybrid import HybridRetriever
from triage.generation.generator import ResponseGenerator
from triage.generation.groundedness import GroundednessScorer
from triage.generation.output_validator import OutputValidator
from triage.tools.registry import ToolRegistry
from triage.tools.executor import ToolExecutor
from triage.tools.argument_binder import ArgumentBinder

log = structlog.get_logger()


async def classify_intent_node(state: TriageState) -> TriageState:
    """Classify intent from message."""
    log.info("node_classify_intent", message_id=state.message_id)

    classifier = IntentClassifier()
    result = classifier.classify(state.message_text)

    state.intents = [
        {"intent": r.intent_name, "confidence": r.confidence}
        for r in result.ranked_intents
    ]
    state.primary_intent = result.top_intent.intent_name if result.top_intent else None
    state.intent_confidence = result.top_intent.confidence if result.top_intent else 0.0
    state.phase = "CLASSIFY"

    return state


async def extract_entities_node(state: TriageState) -> TriageState:
    """Extract entities from message."""
    log.info("node_extract_entities", message_id=state.message_id)

    extractor = RuleBasedEntityExtractor()
    result = extractor.extract(state.message_text, state.message_id)

    state.entities = [
        {
            "entity_type": e.entity_type.name,
            "value": e.value,
            "confidence": e.confidence,
            "is_pii": e.is_pii,
        }
        for e in result.entities
    ]

    # Extract amount if available
    for entity in result.entities:
        if entity.entity_type.name == "AMOUNT":
            try:
                state.extracted_amount = float(
                    entity.normalized_value.replace("$", "").replace(",", "")
                )
            except (ValueError, AttributeError):
                pass

    state.phase = "EXTRACT_ENTITIES"
    return state


async def make_decision_node(state: TriageState) -> TriageState:
    """Determine autonomy level."""
    log.info("node_make_decision", intent=state.primary_intent)

    from triage.models.decision import PolicyInput

    policy_input = PolicyInput(
        intent_name=state.primary_intent or "unknown",
        intent_confidence=state.intent_confidence,
        message_text=state.message_text,
        customer_tier="standard",
        customer_ial=1,
        is_repeat_customer=False,
        previous_resolution_attempts=0,
        extracted_amount=state.extracted_amount,
        safety_flags=state.safety_flags,
    )

    matrix = DecisionMatrix()
    decision = matrix.decide(policy_input)

    state.autonomy_level = decision.autonomy_level.value
    state.autonomy_reason = decision.reason
    state.decision_rule = decision.rule_triggered
    state.phase = "DECIDE"

    return state


async def retrieve_context_node(state: TriageState) -> TriageState:
    """Retrieve context documents."""
    log.info("node_retrieve_context", intent=state.primary_intent)

    # In production: use real retrieval
    state.retrieved_docs = [
        {
            "doc_id": "doc-1",
            "text": "Order information and tracking details",
            "score": 0.85,
        }
    ]
    state.retrieval_query = state.message_text
    state.phase = "RETRIEVE"

    return state


async def generate_response_node(state: TriageState) -> TriageState:
    """Generate response."""
    log.info("node_generate_response", autonomy_level=state.autonomy_level)

    generator = ResponseGenerator()
    system_prompt = f"You are a helpful support agent handling a {state.primary_intent} request."
    result = await generator.generate(
        system_prompt=system_prompt,
        user_message=state.message_text,
        context="\n".join(doc["text"] for doc in state.retrieved_docs),
        max_tokens=500,
    )

    if result.error:
        state.generation_error = result.error
        state.response_text = "I'm unable to help right now. Please try again later."
    else:
        state.response_text = result.response_text

    state.phase = "GENERATE"
    return state


async def validate_output_node(state: TriageState) -> TriageState:
    """Validate generated response."""
    log.info("node_validate_output")

    validator = OutputValidator()
    result = validator.validate(
        state.response_text or "",
        grounding_score=state.grounding_score,
    )

    state.response_valid = result.valid
    if not result.valid:
        state.escalate = True
        state.escalation_reason = f"Response validation failed: {result.reason}"

    scorer = GroundednessScorer()
    grounding = scorer.score(
        state.response_text or "",
        "\n".join(doc["text"] for doc in state.retrieved_docs),
    )
    state.grounding_score = grounding.grounding_score

    state.phase = "VALIDATE"
    return state


async def execute_tools_node(state: TriageState) -> TriageState:
    """Execute tools if needed."""
    log.info("node_execute_tools", autonomy_level=state.autonomy_level)

    # For now: simple mock
    if state.autonomy_level >= AutonomyLevel.L1_SUGGEST.value:
        state.tool_name = "lookup_order"
        state.tool_executed = True
        state.tool_result = {"status": "success"}

    state.phase = "EXECUTE_TOOLS"
    return state


async def escalate_node(state: TriageState) -> TriageState:
    """Escalate to human agent if needed."""
    log.info("node_escalate", reason=state.escalation_reason)

    state.escalate = True
    if not state.escalation_reason:
        state.escalation_reason = "Manual escalation"

    state.escalation_route = "general_queue"
    state.phase = "ESCALATE"

    return state
