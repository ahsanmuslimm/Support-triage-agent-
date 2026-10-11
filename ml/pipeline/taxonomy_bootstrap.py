"""S8.6: Taxonomy Bootstrap.

Auto-discover intent taxonomy from historical data:
- K-means clustering on embeddings (k tuned via silhouette)
- Opus labels each cluster with intent name + confidence
- Admin review UI for label approval/rejection
- Intent merge: combine 2 clusters → merged labels
- Intent split: divide 1 cluster → new labels + separation validation
- Label migration: reclassify historical tickets on merge/split
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

logger = logging.getLogger(__name__)


class LabelStatus(Enum):
    """Status of cluster label."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ClusterLabel:
    """Label for a cluster."""
    cluster_id: int
    intent_name: str
    confidence: float  # 0-1, from Opus
    status: LabelStatus = LabelStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    reviewer_id: Optional[str] = None
    notes: str = ""


@dataclass
class ClusterAnalysis:
    """Analysis of a cluster."""
    cluster_id: int
    size: int
    centroid: np.ndarray
    silhouette: float
    most_common_terms: list[str]
    label: Optional[ClusterLabel] = None


@dataclass
class MergeOperation:
    """Intent merge operation."""
    source_cluster_id: int
    target_cluster_id: int
    merged_intent_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ticket_count_affected: int = 0
    audit_trail: list[str] = field(default_factory=list)


@dataclass
class SplitOperation:
    """Intent split operation."""
    source_cluster_id: int
    new_cluster_ids: list[int]
    new_intent_names: list[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ticket_count_affected: int = 0
    separation_quality: float = 0.0
    audit_trail: list[str] = field(default_factory=list)


class TaxonomyBootstrapper:
    """Auto-discover intent taxonomy."""
    
    def __init__(self, min_k: int = 10, max_k: int = 30):
        self.min_k = min_k
        self.max_k = max_k
        self.clusters = None
        self.labels = {}
        self.merge_history = []
        self.split_history = []
    
    def find_optimal_k(self, embeddings: np.ndarray) -> int:
        """Find optimal k using silhouette score."""
        best_k = self.min_k
        best_score = -1.0
        scores = {}
        
        for k in range(self.min_k, self.max_k + 1):
            kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
            cluster_labels = kmeans.fit_predict(embeddings)
            
            score = silhouette_score(embeddings, cluster_labels)
            scores[k] = score
            
            logger.info(f"k={k}: silhouette={score:.4f}")
            
            if score > best_score:
                best_score = score
                best_k = k
        
        logger.info(f"Selected k={best_k} with silhouette={best_score:.4f}")
        return best_k
    
    def cluster_embeddings(self, embeddings: np.ndarray) -> dict:
        """Cluster embeddings and return cluster info."""
        k = self.find_optimal_k(embeddings)
        
        kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
        cluster_labels = kmeans.fit_predict(embeddings)
        
        # Compute per-cluster stats
        clusters = {}
        for i in range(k):
            mask = cluster_labels == i
            cluster_embeddings = embeddings[mask]
            
            silhouette = silhouette_score(embeddings[mask], np.zeros(np.sum(mask))) if np.sum(mask) > 1 else 0.0
            
            clusters[i] = ClusterAnalysis(
                cluster_id=i,
                size=np.sum(mask),
                centroid=kmeans.cluster_centers_[i],
                silhouette=silhouette,
                most_common_terms=[],  # Would compute from texts
            )
        
        self.clusters = clusters
        return clusters
    
    def label_clusters_with_opus(self, clusters: dict) -> dict[int, ClusterLabel]:
        """Mock: Opus labels each cluster (in real implementation, call Claude API)."""
        labels = {}
        
        # Mock labeling logic
        intent_names = [
            "billing_issue", "account_recovery", "feature_request",
            "technical_support", "refund_request", "login_problem",
            "upgrade_help", "data_export", "api_question", "integration_issue",
        ]
        
        for cluster_id, analysis in clusters.items():
            # Mock: assign random intent
            intent_name = intent_names[cluster_id % len(intent_names)]
            confidence = 0.75 + np.random.rand() * 0.2  # 0.75-0.95
            
            label = ClusterLabel(
                cluster_id=cluster_id,
                intent_name=intent_name,
                confidence=confidence,
                status=LabelStatus.PENDING,
            )
            
            labels[cluster_id] = label
            analysis.label = label
        
        self.labels = labels
        logger.info(f"Labeled {len(labels)} clusters with Opus")
        
        return labels
    
    def review_labels(
        self,
        cluster_id: int,
        approved: bool,
        reviewer_id: str,
        notes: str = "",
    ):
        """Admin reviews cluster label."""
        if cluster_id not in self.labels:
            raise ValueError(f"Cluster {cluster_id} not found")
        
        label = self.labels[cluster_id]
        label.status = LabelStatus.APPROVED if approved else LabelStatus.REJECTED
        label.reviewed_at = datetime.utcnow()
        label.reviewer_id = reviewer_id
        label.notes = notes
        
        logger.info(
            f"Review: cluster {cluster_id} → {'APPROVED' if approved else 'REJECTED'} "
            f"(intent: {label.intent_name})"
        )
    
    def merge_intents(
        self,
        source_cluster_id: int,
        target_cluster_id: int,
        merged_intent_name: str,
        historical_tickets: list[dict],
    ) -> MergeOperation:
        """Merge two clusters, reclassify historical tickets."""
        if source_cluster_id not in self.clusters or target_cluster_id not in self.clusters:
            raise ValueError("Invalid cluster IDs")
        
        source = self.clusters[source_cluster_id]
        target = self.clusters[target_cluster_id]
        
        # Count tickets to migrate
        tickets_affected = sum(
            1 for t in historical_tickets
            if t.get("cluster_id") == source_cluster_id
        )
        
        # Create merged label
        merged_label = ClusterLabel(
            cluster_id=target_cluster_id,
            intent_name=merged_intent_name,
            confidence=min(
                self.labels[source_cluster_id].confidence,
                self.labels[target_cluster_id].confidence,
            ),
            status=LabelStatus.PENDING,
        )
        
        self.labels[target_cluster_id] = merged_label
        
        # Reclassify tickets
        migration_log = []
        for ticket in historical_tickets:
            if ticket.get("cluster_id") == source_cluster_id:
                old_intent = ticket.get("intent")
                ticket["cluster_id"] = target_cluster_id
                ticket["intent"] = merged_intent_name
                migration_log.append(
                    f"Ticket {ticket.get('id')}: {old_intent} → {merged_intent_name}"
                )
        
        # Record operation
        merge_op = MergeOperation(
            source_cluster_id=source_cluster_id,
            target_cluster_id=target_cluster_id,
            merged_intent_name=merged_intent_name,
            ticket_count_affected=tickets_affected,
            audit_trail=migration_log[:10],  # First 10 for logging
        )
        
        self.merge_history.append(merge_op)
        
        logger.info(
            f"Merged clusters {source_cluster_id} → {target_cluster_id}, "
            f"reclassified {tickets_affected} tickets"
        )
        
        return merge_op
    
    def split_intent(
        self,
        source_cluster_id: int,
        new_intent_names: list[str],
        embeddings: np.ndarray,
        cluster_assignments: np.ndarray,
        historical_tickets: list[dict],
    ) -> SplitOperation:
        """Split one cluster into multiple, validate separation."""
        if source_cluster_id not in self.clusters:
            raise ValueError(f"Cluster {source_cluster_id} not found")
        
        # Get source cluster embeddings
        mask = cluster_assignments == source_cluster_id
        source_embeddings = embeddings[mask]
        
        # Sub-cluster with k=len(new_intent_names)
        sub_k = len(new_intent_names)
        if sub_k < 2 or len(source_embeddings) < sub_k:
            raise ValueError(f"Cannot split into {sub_k} clusters")
        
        kmeans = KMeans(n_clusters=sub_k, n_init=10, random_state=42)
        sub_labels = kmeans.fit_predict(source_embeddings)
        
        # Compute separation quality (silhouette)
        separation_quality = silhouette_score(source_embeddings, sub_labels)
        
        # Create new clusters
        new_cluster_ids = list(range(max(self.clusters.keys()) + 1, max(self.clusters.keys()) + 1 + sub_k))
        
        for new_id, intent_name in zip(new_cluster_ids, new_intent_names):
            label = ClusterLabel(
                cluster_id=new_id,
                intent_name=intent_name,
                confidence=0.7,  # Conservative
                status=LabelStatus.PENDING,
            )
            self.labels[new_id] = label
            self.clusters[new_id] = ClusterAnalysis(
                cluster_id=new_id,
                size=np.sum(sub_labels == new_cluster_ids.index(new_id)),
                centroid=kmeans.cluster_centers_[new_cluster_ids.index(new_id)],
                silhouette=separation_quality,
                most_common_terms=[],
                label=label,
            )
        
        # Reclassify tickets
        migration_log = []
        ticket_count = 0
        
        source_indices = np.where(mask)[0]
        for i, ticket in enumerate(historical_tickets):
            if i in source_indices:
                local_idx = list(source_indices).index(i)
                new_sub_label = sub_labels[local_idx]
                new_cluster_id = new_cluster_ids[new_sub_label]
                new_intent_name = new_intent_names[new_sub_label]
                
                old_intent = ticket.get("intent")
                ticket["cluster_id"] = new_cluster_id
                ticket["intent"] = new_intent_name
                ticket_count += 1
                
                if len(migration_log) < 10:
                    migration_log.append(
                        f"Ticket {ticket.get('id')}: {old_intent} → {new_intent_name}"
                    )
        
        split_op = SplitOperation(
            source_cluster_id=source_cluster_id,
            new_cluster_ids=new_cluster_ids,
            new_intent_names=new_intent_names,
            ticket_count_affected=ticket_count,
            separation_quality=separation_quality,
            audit_trail=migration_log,
        )
        
        self.split_history.append(split_op)
        
        logger.info(
            f"Split cluster {source_cluster_id} into {sub_k} clusters, "
            f"separation_quality={separation_quality:.4f}, "
            f"affected {ticket_count} tickets"
        )
        
        return split_op
    
    def export_taxonomy(self, output_path: Path):
        """Export discovered taxonomy."""
        taxonomy = {
            "intents": {},
            "clusters": {},
            "merge_history": [],
            "split_history": [],
        }
        
        for cluster_id, label in self.labels.items():
            if label.status == LabelStatus.APPROVED:
                taxonomy["intents"][label.intent_name] = {
                    "cluster_id": cluster_id,
                    "confidence": label.confidence,
                    "created_at": label.created_at.isoformat(),
                }
        
        for cluster_id, analysis in self.clusters.items():
            taxonomy["clusters"][cluster_id] = {
                "size": analysis.size,
                "silhouette": float(analysis.silhouette),
                "label": self.labels[cluster_id].intent_name if cluster_id in self.labels else None,
            }
        
        for op in self.merge_history:
            taxonomy["merge_history"].append({
                "source": op.source_cluster_id,
                "target": op.target_cluster_id,
                "intent_name": op.merged_intent_name,
                "tickets_affected": op.ticket_count_affected,
                "timestamp": op.timestamp.isoformat(),
            })
        
        for op in self.split_history:
            taxonomy["split_history"].append({
                "source": op.source_cluster_id,
                "new_clusters": op.new_cluster_ids,
                "new_intents": op.new_intent_names,
                "tickets_affected": op.ticket_count_affected,
                "separation_quality": float(op.separation_quality),
                "timestamp": op.timestamp.isoformat(),
            })
        
        with open(output_path, "w") as f:
            json.dump(taxonomy, f, indent=2)
        
        logger.info(f"Exported taxonomy to {output_path}")
        return taxonomy
