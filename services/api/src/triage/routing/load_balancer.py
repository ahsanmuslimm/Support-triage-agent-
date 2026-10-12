"""Load-aware agent assignment with rebalancing and presence tracking."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class AgentLoad:
    """Agent workload information."""

    agent_id: str
    """Agent identifier."""

    current_load: float
    """Current load: open_tickets + estimated_handling_time/60."""

    open_tickets: int = 0
    """Number of open assigned tickets."""

    estimated_handling_time_minutes: int = 0
    """Estimated time (minutes) to handle all tickets."""

    is_online: bool = True
    """Whether agent is currently online."""

    last_activity: datetime = field(default_factory=datetime.utcnow)
    """Last activity timestamp."""

    skills: list[str] = field(default_factory=list)
    """Agent skills/specialties."""

    max_capacity: int = 10
    """Maximum tickets agent can handle."""


@dataclass
class TicketAssignment:
    """Ticket-to-agent assignment."""

    ticket_id: str
    """Ticket identifier."""

    agent_id: str
    """Assigned agent ID."""

    assigned_at: datetime = field(default_factory=datetime.utcnow)
    """Assignment timestamp."""

    acknowledged_at: datetime | None = None
    """When agent acknowledged the ticket."""

    priority: str = "p2"
    """Ticket priority."""

    is_acknowledged: bool = False
    """Whether agent has acknowledged."""


class LoadBalancer:
    """Manage agent load and ticket assignments with rebalancing."""

    # Rebalancing trigger: when agent load > 1.5x average
    REBALANCING_FACTOR = 1.5

    # Stale assignment timeouts
    STALE_TIMEOUT_P1 = timedelta(minutes=5)
    STALE_TIMEOUT_P2 = timedelta(minutes=15)
    STALE_TIMEOUT_P3 = timedelta(minutes=30)

    # Agent offline release timeout
    OFFLINE_RELEASE_TIMEOUT = timedelta(minutes=1)

    def __init__(self) -> None:
        """Initialize load balancer."""
        self.agents: dict[str, AgentLoad] = {}  # agent_id -> AgentLoad
        self.assignments: dict[str, TicketAssignment] = {}  # ticket_id -> Assignment
        self.assignment_history: list[TicketAssignment] = []  # History log

    def register_agent(
        self,
        agent_id: str,
        skills: list[str] | None = None,
        max_capacity: int = 10,
    ) -> None:
        """Register agent in load balancer.

        Args:
            agent_id: Agent identifier.
            skills: Agent skills/specialties.
            max_capacity: Max tickets agent can handle.
        """
        self.agents[agent_id] = AgentLoad(
            agent_id=agent_id,
            skills=skills or [],
            max_capacity=max_capacity,
        )
        log.info("agent_registered", agent_id=agent_id, skills=skills)

    def mark_agent_offline(self, agent_id: str) -> None:
        """Mark agent as offline.

        Args:
            agent_id: Agent identifier.
        """
        if agent_id in self.agents:
            self.agents[agent_id].is_online = False
            log.info("agent_offline", agent_id=agent_id)

    def mark_agent_online(self, agent_id: str) -> None:
        """Mark agent as online.

        Args:
            agent_id: Agent identifier.
        """
        if agent_id in self.agents:
            self.agents[agent_id].is_online = True
            self.agents[agent_id].last_activity = datetime.utcnow()
            log.info("agent_online", agent_id=agent_id)

    def assign_ticket(
        self,
        ticket_id: str,
        priority: str = "p2",
        required_skills: list[str] | None = None,
    ) -> str | None:
        """Assign ticket to available agent.

        Args:
            ticket_id: Ticket ID.
            priority: Ticket priority (p0, p1, p2, p3).
            required_skills: Required agent skills.

        Returns:
            Optional[str]: Assigned agent ID or None if no capacity.
        """
        # Get available agents with required skills
        available_agents = self._get_available_agents(required_skills)

        if not available_agents:
            log.warning("no_available_agents", ticket_id=ticket_id)
            return None

        # Find least-loaded agent
        selected_agent = min(available_agents, key=lambda a: a.current_load)

        # Check capacity
        if selected_agent.current_load >= selected_agent.max_capacity:
            log.warning("agent_at_capacity", agent_id=selected_agent.agent_id, ticket_id=ticket_id)
            return None

        # Assign ticket
        assignment = TicketAssignment(
            ticket_id=ticket_id,
            agent_id=selected_agent.agent_id,
            priority=priority,
        )

        self.assignments[ticket_id] = assignment
        self.assignment_history.append(assignment)

        # Update agent load
        selected_agent.open_tickets += 1
        selected_agent.current_load = self._calculate_load(selected_agent)

        log.info(
            "ticket_assigned",
            ticket_id=ticket_id,
            agent_id=selected_agent.agent_id,
            load=selected_agent.current_load,
        )

        return selected_agent.agent_id

    def acknowledge_ticket(self, ticket_id: str) -> bool:
        """Mark ticket as acknowledged by agent.

        Args:
            ticket_id: Ticket ID.

        Returns:
            bool: True if acknowledged successfully.
        """
        assignment = self.assignments.get(ticket_id)
        if assignment and not assignment.is_acknowledged:
            assignment.acknowledged_at = datetime.utcnow()
            assignment.is_acknowledged = True
            log.info("ticket_acknowledged", ticket_id=ticket_id, agent_id=assignment.agent_id)
            return True
        return False

    def complete_ticket(self, ticket_id: str) -> bool:
        """Complete ticket assignment.

        Args:
            ticket_id: Ticket ID.

        Returns:
            bool: True if completed successfully.
        """
        assignment = self.assignments.pop(ticket_id, None)
        if assignment:
            agent = self.agents.get(assignment.agent_id)
            if agent:
                agent.open_tickets -= 1
                agent.current_load = self._calculate_load(agent)
                log.info("ticket_completed", ticket_id=ticket_id, agent_id=assignment.agent_id)
            return True
        return False

    def check_stale_assignments(self) -> list[tuple[str, str]]:
        """Find unacknowledged tickets that should be reassigned.

        Returns:
            List[tuple[str, str]]: List of (ticket_id, agent_id) to reassign.
        """
        now = datetime.utcnow()
        to_reassign = []

        for assignment in self.assignments.values():
            if assignment.is_acknowledged:
                continue

            # Get stale timeout for priority
            timeout_map = {
                "p0": self.STALE_TIMEOUT_P1,
                "p1": self.STALE_TIMEOUT_P1,
                "p2": self.STALE_TIMEOUT_P2,
                "p3": self.STALE_TIMEOUT_P3,
            }
            timeout = timeout_map.get(assignment.priority, self.STALE_TIMEOUT_P2)

            if now - assignment.assigned_at > timeout:
                to_reassign.append((assignment.ticket_id, assignment.agent_id))
                log.warning(
                    "stale_assignment_detected",
                    ticket_id=assignment.ticket_id,
                    agent_id=assignment.agent_id,
                    age_minutes=(now - assignment.assigned_at).total_seconds() / 60,
                )

        return to_reassign

    def check_offline_releases(self) -> list[tuple[str, str]]:
        """Find tickets from offline agents to release.

        Returns:
            List[tuple[str, str]]: List of (ticket_id, agent_id) to release.
        """
        now = datetime.utcnow()
        to_release = []

        for agent_id, agent in self.agents.items():
            if agent.is_online:
                continue

            # Check if agent been offline too long
            if now - agent.last_activity > self.OFFLINE_RELEASE_TIMEOUT:
                # Find all assignments for this agent
                for assignment in list(self.assignments.values()):
                    if assignment.agent_id == agent_id:
                        to_release.append((assignment.ticket_id, agent_id))
                        log.warning(
                            "offline_release",
                            agent_id=agent_id,
                            ticket_id=assignment.ticket_id,
                        )

        return to_release

    def rebalance(self) -> dict[str, str]:
        """Rebalance tickets if any agent is overloaded.

        Returns:
            Dict[str, str]: Reassignments {ticket_id: new_agent_id}.
        """
        reassignments = {}

        # Calculate average load
        online_agents = [a for a in self.agents.values() if a.is_online]
        if not online_agents:
            return reassignments

        avg_load = sum(a.current_load for a in online_agents) / len(online_agents)

        # Find overloaded agents
        for agent in online_agents:
            if agent.current_load > avg_load * self.REBALANCING_FACTOR:
                # Find tickets to move
                agent_assignments = [
                    a for a in self.assignments.values() if a.agent_id == agent.agent_id
                ]

                # Move lower priority tickets
                for assignment in sorted(agent_assignments, key=lambda a: a.priority):
                    new_agent_id = self.assign_ticket(
                        assignment.ticket_id,
                        assignment.priority,
                    )
                    if new_agent_id:
                        # Remove from old agent
                        self.assignments.pop(assignment.ticket_id, None)
                        agent.open_tickets -= 1
                        agent.current_load = self._calculate_load(agent)

                        reassignments[assignment.ticket_id] = new_agent_id
                        log.info(
                            "ticket_rebalanced",
                            ticket_id=assignment.ticket_id,
                            from_agent=agent.agent_id,
                            to_agent=new_agent_id,
                        )

                        # Check if no longer overloaded
                        if agent.current_load <= avg_load * self.REBALANCING_FACTOR:
                            break

        return reassignments

    def _get_available_agents(self, required_skills: list[str] | None = None) -> list[AgentLoad]:
        """Get online agents with required skills.

        Args:
            required_skills: Required skills (optional).

        Returns:
            List[AgentLoad]: Available agents.
        """
        available = []

        for agent in self.agents.values():
            if not agent.is_online:
                continue

            if required_skills and not any(skill in agent.skills for skill in required_skills):
                continue

            available.append(agent)

        return available

    def _calculate_load(self, agent: AgentLoad) -> float:
        """Calculate agent load.

        Args:
            agent: Agent information.

        Returns:
            float: Load score.
        """
        return agent.open_tickets + (agent.estimated_handling_time_minutes / 60)

    def get_stats(self) -> dict[str, Any]:
        """Get load balancer statistics.

        Returns:
            Dict[str, Any]: Statistics.
        """
        online_agents = [a for a in self.agents.values() if a.is_online]
        total_load = sum(a.current_load for a in online_agents)
        avg_load = total_load / len(online_agents) if online_agents else 0

        return {
            "total_agents": len(self.agents),
            "online_agents": len(online_agents),
            "total_assigned_tickets": len(self.assignments),
            "total_load": total_load,
            "average_load": avg_load,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "load": a.current_load,
                    "open_tickets": a.open_tickets,
                    "is_online": a.is_online,
                }
                for a in online_agents
            ],
        }
