"""Incident clustering with embedding similarity and urgency boost."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
import structlog
import math

log = structlog.get_logger()


@dataclass
class TicketCluster:
    """Group of similar tickets (incident)."""

    cluster_id: str
    """Cluster identifier."""

    ticket_ids: Set[str] = field(default_factory=set)
    """Ticket IDs in cluster."""

    primary_ticket_id: str = ""
    """First ticket in cluster (representative)."""

    created_at: datetime = field(default_factory=datetime.utcnow)
    """Cluster creation time."""

    last_updated: datetime = field(default_factory=datetime.utcnow)
    """Last update time."""

    urgency_boosted: bool = False
    """Whether urgency has been boosted to P1."""

    average_similarity: float = 0.0
    """Average cosine similarity within cluster."""

    runbook_ids: List[str] = field(default_factory=list)
    """Linked runbook IDs for incident response."""

    def add_ticket(self, ticket_id: str, similarity: float = 0.0) -> None:
        """Add ticket to cluster.

        Args:
            ticket_id: Ticket to add.
            similarity: Similarity score to cluster (optional).
        """
        self.ticket_ids.add(ticket_id)
        if not self.primary_ticket_id:
            self.primary_ticket_id = ticket_id
        self.last_updated = datetime.utcnow()


class IncidentClusterer:
    """Cluster similar tickets using embedding similarity."""

    # Similarity threshold for clustering
    SIMILARITY_THRESHOLD = 0.7

    # 30-minute lookback window
    LOOKBACK_WINDOW = timedelta(minutes=30)

    # Urgency boost trigger: 5+ tickets in 10 minutes
    URGENCY_BOOST_THRESHOLD = 5
    URGENCY_BOOST_WINDOW = timedelta(minutes=10)

    def __init__(self, embedding_model: Optional[Any] = None) -> None:
        """Initialize clusterer.

        Args:
            embedding_model: Optional embedding model (use None for mock).
        """
        self.embedding_model = embedding_model
        self.clusters: Dict[str, TicketCluster] = {}  # cluster_id -> TicketCluster
        self.ticket_to_cluster: Dict[str, str] = {}  # ticket_id -> cluster_id
        self.ticket_history: List[tuple[str, str, datetime]] = []  # (ticket_id, summary, timestamp)
        self.runbook_index: Dict[str, List[str]] = {}  # keyword -> [runbook_ids]

    async def cluster_ticket(
        self,
        ticket_id: str,
        summary: str,
        created_at: datetime,
    ) -> Optional[str]:
        """Cluster a new ticket with similar incidents.

        Args:
            ticket_id: New ticket ID.
            summary: Ticket summary for similarity.
            created_at: Ticket creation time.

        Returns:
            Optional[str]: Cluster ID if clustered, None if standalone.
        """
        try:
            log.info("clustering_start", ticket_id=ticket_id, summary_len=len(summary))

            # Get embedding for new ticket
            new_embedding = await self._embed_text(summary)

            # Find similar tickets in lookback window
            cutoff_time = datetime.utcnow() - self.LOOKBACK_WINDOW
            recent_tickets = [
                (tid, summ, ts)
                for tid, summ, ts in self.ticket_history
                if ts > cutoff_time and tid != ticket_id
            ]

            best_cluster_id = None
            best_similarity = 0.0

            for existing_ticket_id, existing_summary, _ in recent_tickets:
                existing_embedding = await self._embed_text(existing_summary)
                similarity = self._cosine_similarity(new_embedding, existing_embedding)

                if similarity > self.SIMILARITY_THRESHOLD and similarity > best_similarity:
                    # Check if existing ticket is in a cluster
                    existing_cluster_id = self.ticket_to_cluster.get(existing_ticket_id)

                    if existing_cluster_id:
                        best_cluster_id = existing_cluster_id
                        best_similarity = similarity
                    elif not best_cluster_id:
                        # Create new cluster for both
                        best_cluster_id = self._create_cluster([existing_ticket_id, ticket_id])
                        best_similarity = similarity

            if best_cluster_id:
                # Add to existing cluster
                cluster = self.clusters[best_cluster_id]
                cluster.add_ticket(ticket_id, best_similarity)
                self.ticket_to_cluster[ticket_id] = best_cluster_id

                log.info(
                    "ticket_clustered",
                    ticket_id=ticket_id,
                    cluster_id=best_cluster_id,
                    similarity=best_similarity,
                )

                # Check urgency boost
                await self._check_urgency_boost(best_cluster_id)

                return best_cluster_id

            # Add to history for future clustering
            self.ticket_history.append((ticket_id, summary, created_at))

            log.info("ticket_not_clustered", ticket_id=ticket_id)
            return None

        except Exception as e:
            log.error("clustering_error", error=str(e), ticket_id=ticket_id)
            return None

    def _create_cluster(self, ticket_ids: List[str]) -> str:
        """Create a new cluster.

        Args:
            ticket_ids: Ticket IDs for cluster.

        Returns:
            str: New cluster ID.
        """
        import uuid

        cluster_id = f"cluster_{str(uuid.uuid4())[:8]}"
        cluster = TicketCluster(cluster_id=cluster_id, primary_ticket_id=ticket_ids[0])

        for tid in ticket_ids:
            cluster.add_ticket(tid)
            self.ticket_to_cluster[tid] = cluster_id

        self.clusters[cluster_id] = cluster

        log.info("cluster_created", cluster_id=cluster_id, ticket_count=len(ticket_ids))

        return cluster_id

    async def _check_urgency_boost(self, cluster_id: str) -> None:
        """Check if cluster should have urgency boosted to P1.

        Args:
            cluster_id: Cluster ID.
        """
        cluster = self.clusters[cluster_id]

        if cluster.urgency_boosted:
            return

        # Count tickets in cluster within URGENCY_BOOST_WINDOW
        cutoff_time = datetime.utcnow() - self.URGENCY_BOOST_WINDOW
        recent_count = sum(
            1
            for tid in cluster.ticket_ids
            if self._ticket_created_after(tid, cutoff_time)
        )

        if recent_count >= self.URGENCY_BOOST_THRESHOLD:
            cluster.urgency_boosted = True
            log.warning(
                "urgency_boosted",
                cluster_id=cluster_id,
                ticket_count=recent_count,
            )

    def _ticket_created_after(self, ticket_id: str, cutoff_time: datetime) -> bool:
        """Check if ticket was created after cutoff time.

        Args:
            ticket_id: Ticket ID.
            cutoff_time: Cutoff datetime.

        Returns:
            bool: True if created after cutoff.
        """
        for tid, _, ts in self.ticket_history:
            if tid == ticket_id:
                return ts > cutoff_time
        return False

    async def _embed_text(self, text: str) -> List[float]:
        """Generate embedding for text.

        Args:
            text: Text to embed.

        Returns:
            List[float]: Embedding vector.
        """
        try:
            if self.embedding_model:
                return await self.embedding_model.embed(text)

            # Mock embedding: hash-based deterministic pseudo-embedding
            import hashlib

            hash_obj = hashlib.md5(text.encode())
            hash_hex = hash_obj.hexdigest()
            embedding = [float(int(hash_hex[i:i+2], 16)) / 255.0 for i in range(0, len(hash_hex), 2)]
            return embedding[:384]

        except Exception as e:
            log.error("embedding_error", error=str(e))
            return [0.0] * 384

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            float: Similarity score (0-1).
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def link_runbook(self, cluster_id: str, runbook_id: str) -> None:
        """Link a runbook to a cluster.

        Args:
            cluster_id: Cluster ID.
            runbook_id: Runbook ID.
        """
        cluster = self.clusters.get(cluster_id)
        if cluster and runbook_id not in cluster.runbook_ids:
            cluster.runbook_ids.append(runbook_id)
            log.info("runbook_linked", cluster_id=cluster_id, runbook_id=runbook_id)

    def get_cluster(self, cluster_id: str) -> Optional[TicketCluster]:
        """Get cluster by ID.

        Args:
            cluster_id: Cluster ID.

        Returns:
            Optional[TicketCluster]: Cluster or None.
        """
        return self.clusters.get(cluster_id)

    def get_related_tickets(self, ticket_id: str) -> List[str]:
        """Get related tickets in same cluster.

        Args:
            ticket_id: Ticket ID.

        Returns:
            List[str]: Related ticket IDs (excluding input).
        """
        cluster_id = self.ticket_to_cluster.get(ticket_id)
        if not cluster_id:
            return []

        cluster = self.clusters[cluster_id]
        return list(cluster.ticket_ids - {ticket_id})

    def get_stats(self) -> Dict[str, Any]:
        """Get clustering statistics.

        Returns:
            Dict[str, Any]: Statistics.
        """
        total_tickets = len(self.ticket_history)
        clustered_tickets = len(self.ticket_to_cluster)
        boosted_clusters = sum(1 for c in self.clusters.values() if c.urgency_boosted)

        return {
            "total_tickets": total_tickets,
            "clustered_tickets": clustered_tickets,
            "total_clusters": len(self.clusters),
            "urgency_boosted_clusters": boosted_clusters,
            "lookback_window_minutes": int(self.LOOKBACK_WINDOW.total_seconds() / 60),
        }
