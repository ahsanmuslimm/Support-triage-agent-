"""Bind extracted entities to tool arguments."""

from typing import Dict, Any, List, Optional
import structlog

from triage.models.entity import ExtractedEntity, EntityType
from triage.tools.registry import ToolSpec

log = structlog.get_logger()


class ArgumentBinder:
    """Bind extracted entities to tool argument slots."""

    # Mapping from EntityType to tool argument names
    ENTITY_TO_ARG = {
        EntityType.ORDER_ID: "order_id",
        EntityType.AMOUNT: "amount",
        EntityType.EMAIL: "to",
        EntityType.ACCOUNT_ID: "account_id",
        EntityType.PHONE: "phone",
    }

    @staticmethod
    def bind(entities: List[ExtractedEntity], tool_spec: ToolSpec) -> Dict[str, Any]:
        """Bind entities to tool arguments.

        Args:
            entities: List of extracted entities
            tool_spec: Tool specification

        Returns:
            Dict of bound arguments

        Raises:
            ValueError: If required args not bound
        """
        bound_args: Dict[str, Any] = {}

        # Bind each entity to its argument
        for entity in entities:
            arg_name = ArgumentBinder.ENTITY_TO_ARG.get(entity.entity_type)
            if arg_name and arg_name in tool_spec.required_args:
                # Use normalized value if available
                value = entity.normalized_value or entity.value

                # Type conversion based on required type
                required_type = tool_spec.required_args[arg_name]
                if required_type == "float":
                    try:
                        value = float(value.replace("$", "").replace(",", ""))
                    except (ValueError, AttributeError):
                        pass

                bound_args[arg_name] = value
                log.debug(
                    "entity_bound_to_arg",
                    entity_type=entity.entity_type,
                    arg_name=arg_name,
                    tool=tool_spec.name,
                )

        # Check required args are present
        missing = set(tool_spec.required_args.keys()) - set(bound_args.keys())
        if missing:
            raise ValueError(
                f"Missing required arguments for {tool_spec.name}: {', '.join(missing)}"
            )

        return bound_args
