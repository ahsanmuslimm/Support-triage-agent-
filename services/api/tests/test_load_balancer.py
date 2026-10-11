"""Tests for load-aware agent assignment and rebalancing."""

import pytest
from datetime import datetime, timedelta
from triage.routing.load_balancer import (
    LoadBalancer,
    AgentLoad,
    TicketAssignment,
)


@pytest.fixture
def load_balancer():
    """Create test load balancer."""
    return LoadBalancer()


class TestAgentRegistration:
    """Test agent registration."""

    def test_register_agent(self, load_balancer):
        """Test registering an agent."""
        load_balancer.register_agent(
            "agent_1",
            skills=["billing", "technical"],
            max_capacity=10,
        )

        assert "agent_1" in load_balancer.agents
        agent = load_balancer.agents["agent_1"]
        assert agent.is_online
        assert "billing" in agent.skills

    def test_multiple_agents(self, load_balancer):
        """Test registering multiple agents."""
        for i in range(3):
            load_balancer.register_agent(f"agent_{i}", max_capacity=5)

        assert len(load_balancer.agents) == 3


class TestTicketAssignment:
    """Test ticket assignment logic."""

    def test_assign_ticket_to_least_loaded(self, load_balancer):
        """Test ticket assigned to least-loaded agent."""
        load_balancer.register_agent("agent_1", max_capacity=10)
        load_balancer.register_agent("agent_2", max_capacity=10)

        # Give agent_1 some load
        load_balancer.agents["agent_1"].open_tickets = 3
        load_balancer.agents["agent_1"].current_load = 3.0

        # Assign ticket
        assigned_agent = load_balancer.assign_ticket("ticket_1", priority="p2")

        # Should go to agent_2 (least loaded)
        assert assigned_agent == "agent_2"

    def test_skill_matching(self, load_balancer):
        """Test skill-based assignment."""
        load_balancer.register_agent("billing_agent", skills=["billing"])
        load_balancer.register_agent("tech_agent", skills=["technical"])

        # Assign ticket requiring billing skill
        assigned = load_balancer.assign_ticket(
            "ticket_billing",
            required_skills=["billing"],
        )

        assert assigned == "billing_agent"

    def test_capacity_check(self, load_balancer):
        """Test agent capacity limits."""
        load_balancer.register_agent("agent_full", max_capacity=1)

        # Assign first ticket
        load_balancer.assign_ticket("ticket_1")
        assert load_balancer.agents["agent_full"].open_tickets == 1

        # Assign second ticket (should fail)
        result = load_balancer.assign_ticket("ticket_2")

        assert result is None  # No capacity


class TestAcknowledgement:
    """Test ticket acknowledgement."""

    def test_acknowledge_ticket(self, load_balancer):
        """Test acknowledging a ticket."""
        load_balancer.register_agent("agent_1")
        agent_id = load_balancer.assign_ticket("ticket_1")

        success = load_balancer.acknowledge_ticket("ticket_1")

        assert success
        assignment = load_balancer.assignments["ticket_1"]
        assert assignment.is_acknowledged

    def test_acknowledge_nonexistent_ticket(self, load_balancer):
        """Test acknowledging ticket that doesn't exist."""
        result = load_balancer.acknowledge_ticket("nonexistent")

        assert not result


class TestStaleAssignments:
    """Test stale assignment detection and reclaim."""

    def test_detect_stale_p1(self, load_balancer):
        """Test detecting stale P1 tickets (5 min timeout)."""
        load_balancer.register_agent("agent_1")

        # Assign P1 ticket
        load_balancer.assign_ticket("ticket_p1", priority="p1")

        # Manually age the assignment
        load_balancer.assignments["ticket_p1"].assigned_at = (
            datetime.utcnow() - timedelta(minutes=6)
        )

        stale = load_balancer.check_stale_assignments()

        assert len(stale) > 0
        assert stale[0][0] == "ticket_p1"

    def test_detect_stale_p2(self, load_balancer):
        """Test detecting stale P2 tickets (15 min timeout)."""
        load_balancer.register_agent("agent_1")

        load_balancer.assign_ticket("ticket_p2", priority="p2")
        load_balancer.assignments["ticket_p2"].assigned_at = (
            datetime.utcnow() - timedelta(minutes=16)
        )

        stale = load_balancer.check_stale_assignments()

        assert len(stale) > 0

    def test_acknowledged_not_stale(self, load_balancer):
        """Test acknowledged tickets are not marked stale."""
        load_balancer.register_agent("agent_1")

        load_balancer.assign_ticket("ticket_1", priority="p1")
        load_balancer.acknowledge_ticket("ticket_1")

        # Age it
        load_balancer.assignments["ticket_1"].assigned_at = (
            datetime.utcnow() - timedelta(minutes=10)
        )

        stale = load_balancer.check_stale_assignments()

        # Should not be in stale list (acknowledged)
        assert len([s for s in stale if s[0] == "ticket_1"]) == 0


class TestOfflineRelease:
    """Test releasing tickets from offline agents."""

    def test_offline_agent_release(self, load_balancer):
        """Test tickets are released from offline agents."""
        load_balancer.register_agent("agent_1")

        # Assign ticket
        load_balancer.assign_ticket("ticket_1")

        # Mark offline and age
        load_balancer.mark_agent_offline("agent_1")
        load_balancer.agents["agent_1"].last_activity = (
            datetime.utcnow() - timedelta(minutes=2)
        )

        to_release = load_balancer.check_offline_releases()

        assert len(to_release) > 0
        assert to_release[0][0] == "ticket_1"

    def test_online_agent_not_released(self, load_balancer):
        """Test online agents' tickets are not released."""
        load_balancer.register_agent("agent_1")
        load_balancer.assign_ticket("ticket_1")

        to_release = load_balancer.check_offline_releases()

        assert len(to_release) == 0


class TestRebalancing:
    """Test load rebalancing."""

    def test_rebalance_overloaded_agent(self, load_balancer):
        """Test rebalancing when agent is overloaded."""
        load_balancer.register_agent("agent_1", max_capacity=20)
        load_balancer.register_agent("agent_2", max_capacity=20)

        # Give agent_1 high load (simulated)
        load_balancer.agents["agent_1"].current_load = 15.0
        load_balancer.agents["agent_1"].open_tickets = 5

        # Assign tickets to agent_1
        for i in range(5):
            load_balancer.assign_ticket(f"ticket_{i}")

        # Give agent_2 low load
        load_balancer.agents["agent_2"].current_load = 1.0
        load_balancer.agents["agent_2"].open_tickets = 0

        reassignments = load_balancer.rebalance()

        # Some tickets should be reassigned
        assert len(reassignments) > 0

    def test_rebalance_factor(self, load_balancer):
        """Test rebalancing triggers at 1.5x average load."""
        assert load_balancer.REBALANCING_FACTOR == 1.5


class TestAgentPresence:
    """Test agent online/offline status."""

    def test_mark_offline(self, load_balancer):
        """Test marking agent offline."""
        load_balancer.register_agent("agent_1")
        load_balancer.mark_agent_offline("agent_1")

        assert not load_balancer.agents["agent_1"].is_online

    def test_mark_online(self, load_balancer):
        """Test marking agent online."""
        load_balancer.register_agent("agent_1")
        load_balancer.mark_agent_offline("agent_1")
        load_balancer.mark_agent_online("agent_1")

        assert load_balancer.agents["agent_1"].is_online

    def test_online_agent_available(self, load_balancer):
        """Test only online agents are available for assignment."""
        load_balancer.register_agent("online_agent")
        load_balancer.register_agent("offline_agent")

        load_balancer.mark_agent_offline("offline_agent")

        assigned = load_balancer.assign_ticket("ticket_1")

        # Should go to online agent
        assert assigned == "online_agent"


class TestStats:
    """Test load balancer statistics."""

    def test_get_stats(self, load_balancer):
        """Test retrieving statistics."""
        load_balancer.register_agent("agent_1")
        load_balancer.register_agent("agent_2")

        load_balancer.assign_ticket("ticket_1")

        stats = load_balancer.get_stats()

        assert stats["total_agents"] == 2
        assert stats["online_agents"] == 2
        assert stats["total_assigned_tickets"] == 1

    def test_completion_updates_load(self, load_balancer):
        """Test completing ticket reduces agent load."""
        load_balancer.register_agent("agent_1")
        agent_id = load_balancer.assign_ticket("ticket_1")

        initial_tickets = load_balancer.agents[agent_id].open_tickets
        load_balancer.complete_ticket("ticket_1")

        final_tickets = load_balancer.agents[agent_id].open_tickets

        assert final_tickets == initial_tickets - 1
