"""LangGraph definition for triage agent."""

import structlog
from typing import Literal

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    StateGraph = None
    END = None
    SqliteSaver = None

from triage.models.triage_state import TriageState
from triage.agent.nodes import (
    classify_intent_node,
    extract_entities_node,
    make_decision_node,
    retrieve_context_node,
    generate_response_node,
    validate_output_node,
    execute_tools_node,
    escalate_node,
)

log = structlog.get_logger()


class TriageAgentGraph:
    """LangGraph for triage orchestration."""

    def __init__(self):
        """Initialize triage graph."""
        if StateGraph is None:
            raise RuntimeError("LangGraph not installed")

        self.graph = self._build_graph()
        self.checkpointer = self._init_checkpointer()

    def _build_graph(self) -> StateGraph:
        """Build LangGraph with nodes and edges."""
        workflow = StateGraph(TriageState)

        # Add nodes
        workflow.add_node("classify_intent", classify_intent_node)
        workflow.add_node("extract_entities", extract_entities_node)
        workflow.add_node("make_decision", make_decision_node)
        workflow.add_node("retrieve_context", retrieve_context_node)
        workflow.add_node("generate_response", generate_response_node)
        workflow.add_node("validate_output", validate_output_node)
        workflow.add_node("execute_tools", execute_tools_node)
        workflow.add_node("escalate", escalate_node)

        # Add edges
        workflow.set_entry_point("classify_intent")

        workflow.add_edge("classify_intent", "extract_entities")
        workflow.add_edge("extract_entities", "make_decision")

        # Route based on autonomy level and confidence
        def route_after_decision(state: TriageState) -> Literal["escalate", "retrieve_context"]:
            if state.autonomy_level == 0:
                return "escalate"
            return "retrieve_context"

        workflow.add_conditional_edges("make_decision", route_after_decision)

        workflow.add_edge("retrieve_context", "generate_response")
        workflow.add_edge("generate_response", "validate_output")

        # Route based on validation
        def route_after_validation(state: TriageState) -> Literal["execute_tools", "escalate", END]:
            if not state.response_valid:
                return "escalate"
            if state.autonomy_level >= 1:
                return "execute_tools"
            return END

        workflow.add_conditional_edges("validate_output", route_after_validation)

        # Route after tool execution
        def route_after_tools(state: TriageState) -> Literal["escalate", END]:
            if state.tool_error:
                return "escalate"
            return END

        workflow.add_conditional_edges("execute_tools", route_after_tools)

        workflow.add_edge("escalate", END)

        log.info("triage_graph_built", nodes=8, edges="conditional_routing")

        return workflow.compile(checkpointer=self._init_checkpointer())

    @staticmethod
    def _init_checkpointer():
        """Initialize state checkpointer."""
        try:
            if SqliteSaver:
                return SqliteSaver.from_conn_string(":memory:")
        except Exception as e:
            log.warning("checkpointer_init_failed", error=str(e))
        return None

    def run(
        self,
        message_text: str,
        customer_id: str,
        tenant_id: str,
        conversation_id: str = "default",
    ) -> TriageState:
        """Run triage agent on message.

        Args:
            message_text: User message
            customer_id: Customer ID
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Final TriageState
        """
        log.info(
            "triage_run_start",
            customer_id=customer_id,
            tenant_id=tenant_id,
        )

        initial_state = TriageState(
            message_id=f"msg-{hash(message_text) % 1000000}",
            message_text=message_text,
            customer_id=customer_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

        # Run graph synchronously
        try:
            result = self.graph.invoke(initial_state)
            log.info("triage_run_complete", phase=result.phase)
            return result
        except Exception as e:
            log.error("triage_run_error", error=str(e))
            initial_state.escalate = True
            initial_state.escalation_reason = f"Graph execution failed: {str(e)}"
            return initial_state
