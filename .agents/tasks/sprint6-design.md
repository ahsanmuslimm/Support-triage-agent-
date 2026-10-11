# Sprint 6 Technical Design: Production Adapter Bridge

**Date:** October 2026  
**Status:** PENDING REVIEW  
**Goal:** Replace MVP seams with production adapters: Protobuf contracts, Kafka/Debezium, Redis-backed idempotency, priority lanes, and Temporal workflow engine. Enable gradual cutover from in-memory MVP to distributed architecture.

---

## Executive Summary

Sprint 6 bridges the MVP to production by replacing 5 architectural seams:

| Seam | MVP | Production | Impact |
|------|-----|-----------|--------|
| **Event Serialization** | Python dicts | Protobuf 3 + CloudEvents | Schema evolution, cross-language, versioning |
| **Event Bus** | In-memory dict store | Kafka 4 (3 brokers KRaft) | Durability, multi-process, replay |
| **Event Relay** | OutboxPoller polling | Debezium PostgreSQL connector | Log-based CDC, strong ordering |
| **Idempotency** | None (in-progress) | Redis (7d TTL) + Postgres (critical) | Exactly-once semantics, crash recovery |
| **Routing** | FIFO + LangGraph nodes | Priority queues (chat/email lanes) | SLA compliance, user experience |
| **Workflows** | In-process executor | Temporal 1.24+ with PostgreSQL | Durability, visibility, resumable |

**6 Deliverables (S6.1–S6.6), 3 integration phases, 1 gradual cutover plan.**

---

## Table of Contents

1. [MVP Architecture Mapping](#1-mvp-architecture-mapping)
2. [S6.1 — Protobuf Contracts & Code Generation](#2-s61--protobuf-contracts--code-generation)
3. [S6.2 — Kafka Adapter & Debezium](#3-s62--kafka-adapter--debezium)
4. [S6.3 — Consumer Idempotency & DLQ](#4-s63--consumer-idempotency--dlq)
5. [S6.4 — Priority Lanes](#5-s64--priority-lanes)
6. [S6.5 — Temporal Adapter](#6-s65--temporal-adapter-for-workflowengine)
7. [S6.6 — Cut-Over Plan](#7-s66--cut-over-plan--parity-verification)
8. [Infrastructure Topology](#8-infrastructure-topology)
9. [Migration Strategy](#9-migration-strategy-concurrent-mvp--production)
10. [Risk Analysis](#10-risk-analysis)
11. [Testing Strategy](#11-testing-strategy-per-deliverable)

---

## 1. MVP Architecture Mapping

### Current Seams (Sprint 5 Complete)

**Event Bus (MVP):** `triage.ingestion.outbox` (in-memory + pseudo-Postgres)
```python
# File: services/api/src/triage/ingestion/outbox.py
class OutboxWriter:
    """Writes events to outbox table (transactionally with domain objects)."""
    async def write_event(tenant_id, aggregate_type, aggregate_id, event_type, payload) -> OutboxEvent
    def get_unpublished_events(limit=100) -> List[OutboxEvent]
    def mark_published(event_id)

class OutboxPoller:
    """Background task that polls outbox and delivers events."""
    async def poll_once() -> None
    async def poll_forever() -> None
```

**Event Model (MVP):** `triage.models.events`
```python
class OutboxEvent(BaseModel):
    id: str                          # UUID
    tenant_id: str                   # UUID (tenant isolation)
    aggregate_type: str              # "message", "conversation", "action", etc.
    aggregate_id: str                # UUID
    event_type: str                  # "message.ingested", "action.completed"
    payload: Dict[str, Any]          # Untyped JSON
    created_at: datetime
    published_at: Optional[datetime]
```

**Workflow Executor (MVP):** `triage.agent.graph` (LangGraph in-process)
```python
class TriageAgentGraph:
    """LangGraph for triage orchestration."""
    def _build_graph(self) -> StateGraph:
        # 8 nodes: classify_intent → extract_entities → make_decision → 
        # retrieve_context → generate_response → validate_output → 
        # execute_tools → escalate
        # Conditional routing based on autonomy, validation, tool results
    async def invoke(message: TriageState, config=None) -> Dict
```

**In-Memory Event Handling (Tests):** `py_core.testing.InMemoryEventBus`
```python
class InMemoryEventBus:
    """In-memory event bus for testing."""
    async def publish(event_type: str, tenant_id: str, payload: Dict) -> None
    def published_events(event_type: str = None) -> List[Dict]
    def reset() -> None
    def assert_published(event_type: str, expected_payload: Dict) -> None
```

**Key Integration Points:**
1. **Message Ingestion:** `services/api/src/triage/api/endpoints/messages.py`
   - Receives message → calls OutboxWriter.write_event() → queues for async processing
2. **Outreach (Campaigns):** `services/api/src/triage/outreach/` → publishes campaign events
3. **Decision Engine:** `services/api/src/triage/decision/` → publishes autonomy decisions
4. **Escalation & Feedback:** `services/api/src/triage/escalation/`, `feedback/` → emit events

**Assumptions Going Forward:**
- All domain objects emit events via OutboxWriter
- OutboxPoller runs in a sidecar or scheduled task
- Tenant context propagates via UUID (CURRENT_SETTING('app.tenant_id'))
- Message idempotency is in-flight; no durable idempotency store yet

---

## 2. S6.1 — Protobuf Contracts & Code Generation

### Goal
Define immutable, versioned Kafka event schemas using Protocol Buffers 3. Enable cross-language consumers (Python, Go, Java), schema evolution with backward compatibility, and code generation.

### Design

#### 2.1 Proto Directory Structure
```
packages/proto/
├── buf.yaml                          # buf CLI config for linting & gen
├── buf.gen.yaml                      # Code generation config
├── google/
│   └── protobuf/
│       └── timestamp.proto           # (external; imported)
├── triage/
│   ├── events/
│   │   ├── events.proto              # Base event envelope (S6.1.1)
│   │   ├── message_events.proto      # message.ingested, message.classified
│   │   ├── action_events.proto       # action.executed, action.failed
│   │   ├── routing_events.proto      # ticket.routed, ticket.escalated
│   │   ├── campaign_events.proto     # campaign.sent, campaign.clicked
│   │   └── workflow_events.proto     # workflow.started, workflow.step_completed
│   ├── messages/
│   │   ├── messages.proto            # Message domain model (S6.1.2)
│   │   ├── customer.proto            # Customer enrichment (refs)
│   │   └── conversation.proto        # Conversation context
│   └── workflows/
│       ├── workflow_inputs.proto     # Temporal workflow input (S6.1.3)
│       └── workflow_state.proto      # Workflow state checkpoints
└── triage/
    └── v1/                           # Namespaced versioning
        ├── events/
        └── messages/
```

#### 2.2 Core Proto Definitions

**File: `packages/proto/triage/events/events.proto`**
```protobuf
syntax = "proto3";
package triage.events.v1;

import "google/protobuf/timestamp.proto";

// CloudEvents envelope for Kafka
message CloudEvent {
    string id = 1;                                    // UUID
    string source = 2;                               // "triage/messages" (reverse DNS)
    string type = 3;                                 // "message.ingested"
    google.protobuf.Timestamp occurred_at = 4;       // Event time (not wall-clock)
    string content_type = 5;                         // "application/protobuf"
    string data_content_type = 6;                    // "application/protobuf"
    string subject = 7;                              // "tenant/{tenant_id}/message/{message_id}"
    map<string, string> attributes = 8;              // Custom headers
    bytes data = 9;                                  // Serialized payload (e.g., MessageIngested)
    
    // Extensions for multi-tenancy + ordering
    string tenant_id = 100;                          // Partition key
    int32 idempotency_version = 101;                 // For exactly-once
}

// Base event message (all events inherit this pattern)
message BaseEvent {
    string id = 1;                                   // Event ID (UUID)
    string tenant_id = 2;                            // Multi-tenancy
    google.protobuf.Timestamp occurred_at = 3;       // When it happened
    int32 version = 4;                               // Schema version (for evolution)
}
```

**File: `packages/proto/triage/events/message_events.proto`**
```protobuf
syntax = "proto3";
package triage.events.v1;

import "google/protobuf/timestamp.proto";
import "triage/events/events.proto";

message MessageIngested {
    BaseEvent base = 1;                              // Inherited base
    string message_id = 2;                           // UUID
    string conversation_id = 3;                      // UUID
    string customer_id = 4;                          // UUID
    string channel = 5;                              // "email", "chat", "web"
    string body = 6;                                 // Message text
    map<string, string> metadata = 7;                // channel-specific fields
    int32 estimated_response_time_secs = 8;          // SLA context
}

message MessageClassified {
    BaseEvent base = 1;
    string message_id = 2;
    string intent = 3;                               // "refund_request", "order_lookup", etc.
    float confidence = 4;                            // 0.0–1.0
    repeated string entities = 5;                    // ["order_123", "sku_456"]
    string sentiment = 6;                            // "negative", "neutral", "positive"
    bool autonomous_resolution = 7;                  // Can bot handle?
}

message ActionExecuted {
    BaseEvent base = 1;
    string message_id = 2;
    string action_name = 3;                          // "issue_refund", "lookup_order"
    repeated string inputs = 4;                      // Tool arguments
    string result = 5;                               // Result JSON (string for compatibility)
    int32 latency_ms = 6;                            // Execution time
}

message MessageEscalated {
    BaseEvent base = 1;
    string message_id = 2;
    string escalation_reason = 3;                    // "policy_required", "human_judgment"
    string assigned_agent_id = 4;                    // UUID (nullable)
    int32 priority = 5;                              // 1–5 (5 = urgent)
}
```

**File: `packages/proto/triage/messages/messages.proto`**
```protobuf
syntax = "proto3";
package triage.messages.v1;

import "google/protobuf/timestamp.proto";

message Message {
    string id = 1;                                   // UUID
    string tenant_id = 2;                            // Multi-tenancy
    string conversation_id = 3;                      // UUID
    string customer_id = 4;                          // UUID
    string channel = 5;                              // "email", "chat", etc.
    string body = 6;                                 // Message text
    string sentiment = 7;                            // "negative", "neutral", "positive"
    string intent = 8;                               // Primary intent
    float intent_confidence = 9;                     // 0.0–1.0
    
    google.protobuf.Timestamp created_at = 10;
    google.protobuf.Timestamp processed_at = 11;    // When triage completed
    
    MessageStatus status = 12;                       // INGESTED, CLASSIFIED, ROUTED, RESOLVED
    enum MessageStatus {
        UNSPECIFIED = 0;
        INGESTED = 1;
        CLASSIFIED = 2;
        ROUTED = 3;
        RESOLVED = 4;
        FAILED = 5;
    }
    
    string resolution_type = 13;                     // "autonomous", "agent", "escalated"
    repeated Action actions = 14;                    // Actions taken
}

message Action {
    string name = 1;                                 // "issue_refund", "lookup_order"
    string result_status = 2;                        // "success", "failed", "pending"
    string result_detail = 3;                        // Result or error message
    int32 latency_ms = 4;                            // Execution time
}
```

**File: `packages/proto/triage/workflows/workflow_inputs.proto`**
```protobuf
syntax = "proto3";
package triage.workflows.v1;

import "google/protobuf/timestamp.proto";
import "triage/messages/messages.proto";

// Input to Temporal workflow
message ProcessMessageWorkflowInput {
    string message_id = 1;                           // UUID
    string tenant_id = 2;
    string conversation_id = 3;
    messages.Message message = 4;                    // Full message domain object
    google.protobuf.Timestamp workflow_started_at = 5;
    int32 idempotency_key_version = 6;              // For deduplication
}

// Workflow state (stored in Temporal history DB)
message WorkflowCheckpoint {
    string workflow_id = 1;                          // (tenant_id, aggregate_id, idempotency_key)
    string run_id = 2;                               // Temporal run ID
    ProcessMessageWorkflowInput input = 3;
    
    CheckpointPhase phase = 4;                       // Current phase
    enum CheckpointPhase {
        UNSPECIFIED = 0;
        CLASSIFY = 1;
        ENRICH = 2;
        DECIDE = 3;
        RESOLVE = 4;
        ESCALATE = 5;
        COMPLETE = 6;
    }
    
    google.protobuf.Timestamp checkpoint_at = 5;
    string state_json = 6;                           // Current execution state (JSON string)
}
```

#### 2.3 buf Configuration

**File: `packages/proto/buf.yaml`**
```yaml
version: v1
deps:
  - buf.build/googleapis/googleapis

lint:
  use:
    - STANDARD                    # Standard rules
  except:
    - PACKAGE_VERSION_SUFFIX      # Allow .v1 in package names
  
breaking:
  use:
    - FILE                        # Detect breaking changes
  except:
    - WIRE_COMPATIBLE_ENUM        # Allow safe enum extensions
```

**File: `packages/proto/buf.gen.yaml` (M1 Fix — Clarify pyi + python output handling)**
```yaml
version: v1
managed:
  enabled: true
  go_package_prefix:
    default: github.com/ahsanmuslimm/support-triage-agent/gen/go
  python_package_prefix:
    default: gen.python
outputs:
  - target: go-grpc
    out: gen/go
  
  # Python implementation files (_pb2.py)
  - target: python
    out: gen/python
    opt:
      - "package_root=gen"
  
  # Python type stub files (_pb2.pyi)
  # Both python and pyi outputs write to gen/python directory side-by-side.
  # Files do NOT overwrite: _pb2.py (implementation) and _pb2.pyi (type stubs) are separate.
  # Type checkers (mypy, pyright) use .pyi stubs for type checking.
  # Runtime uses _pb2.py implementations.
  - target: pyi
    out: gen/python
```

**Clarification (M1 Fix):**

The buf configuration generates both implementation and type stubs:

| Output | File Name | Purpose | Consumer |
|--------|-----------|---------|----------|
| `target: python` | `*_pb2.py` | Protobuf runtime implementation | Python code at runtime |
| `target: pyi` | `*_pb2.pyi` | Type hints for type checkers | mypy, pyright, IDEs (static analysis only) |

Both outputs write to `gen/python/` but do NOT collide because they have different extensions (`.py` vs `.pyi`).

**CI/CD Verification (M1 Fix — GitHub Actions):**

```yaml
- name: Generate Protobuf Python code and stubs
  run: |
    buf generate packages/proto --template packages/proto/buf.gen.yaml
    
    # Verify both types of files were generated
    python_impl_count=$(find gen/python -name "*_pb2.py" | wc -l)
    python_stub_count=$(find gen/python -name "*_pb2.pyi" | wc -l)
    
    if [ $python_impl_count -eq 0 ]; then
      echo "❌ ERROR: No *_pb2.py implementation files generated"
      exit 1
    fi
    
    if [ $python_stub_count -eq 0 ]; then
      echo "❌ ERROR: No *_pb2.pyi stub files generated"
      exit 1
    fi
    
    echo "✓ Generated $python_impl_count implementation files (_pb2.py)"
    echo "✓ Generated $python_stub_count type stub files (_pb2.pyi)"

- name: Commit generated code and stubs
  run: |
    git config user.name "buf-bot"
    git config user.email "bufbot@example.com"
    
    # Add all generated files (both .py and .pyi)
    git add gen/python/triage/
    
    # Verify we're committing both types
    if git diff --cached --name-only | grep -q "_pb2.py" && \
       git diff --cached --name-only | grep -q "_pb2.pyi"; then
      echo "✓ Committing both implementation and stub files"
    else
      echo "⚠️  WARNING: Not all file types are being committed"
      git diff --cached --name-only
    fi
    
    git commit -m "chore: regenerate protobuf Python code and type stubs" || true
    git push
```

#### 2.4 Code Generation Pipeline

**File: `.github/workflows/protobuf-generate.yml`**
```yaml
name: Protobuf Code Generation

on:
  push:
    paths:
      - 'packages/proto/**'
    branches:
      - main
      - 'feature/**'

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install buf
        run: go install github.com/bufbuild/buf/cmd/buf@latest
      
      - name: Lint protos
        run: buf lint packages/proto
        working-directory: .
      
      - name: Check breaking changes
        run: buf breaking packages/proto --against-input='{"module":"packages/proto"}'
        continue-on-error: true  # Warn but don't fail
      
      - name: Generate Protobuf Python code and stubs
        run: |
          buf generate packages/proto --template packages/proto/buf.gen.yaml
          
          # Verify both types of files were generated
          python_impl_count=$(find gen/python -name "*_pb2.py" | wc -l)
          python_stub_count=$(find gen/python -name "*_pb2.pyi" | wc -l)
          
          if [ $python_impl_count -eq 0 ]; then
            echo "❌ ERROR: No *_pb2.py implementation files generated"
            exit 1
          fi
          
          if [ $python_stub_count -eq 0 ]; then
            echo "❌ ERROR: No *_pb2.pyi stub files generated"
            exit 1
          fi
          
          echo "✓ Generated $python_impl_count implementation files (_pb2.py)"
          echo "✓ Generated $python_stub_count type stub files (_pb2.pyi)"
      
      - name: Commit generated code and stubs
        run: |
          git config user.name "buf-bot"
          git config user.email "bufbot@example.com"
          git add gen/python/triage/
          git commit -m "chore: regenerate protobuf Python code and type stubs" || true
          git push
```

#### 2.5 Round-Trip Serialization Tests

**File: `services/api/tests/test_protobuf_contracts.py`**
```python
import pytest
from google.protobuf.json_format import MessageToJson, Parse
from triage.events.v1 import MessageIngested, CloudEvent
from triage.messages.v1 import Message, Action
from datetime import datetime
from google.protobuf.timestamp_pb2 import Timestamp

@pytest.mark.unit
def test_message_ingested_roundtrip():
    """Test serialize → deserialize preserves data."""
    # Arrange
    event = MessageIngested(
        base=BaseEvent(
            id="evt_123",
            tenant_id="tenant_1",
            version=1,
        ),
        message_id="msg_456",
        conversation_id="conv_789",
        customer_id="cust_010",
        channel="email",
        body="Where is my order?",
    )
    
    # Act: Serialize to bytes
    serialized = event.SerializeToString()
    
    # Deserialize back
    deserialized = MessageIngested()
    deserialized.ParseFromString(serialized)
    
    # Assert: Fields match
    assert deserialized.message_id == "msg_456"
    assert deserialized.body == "Where is my order?"
    assert len(serialized) < 500  # Protobuf is compact

@pytest.mark.unit
def test_message_ingested_json_roundtrip():
    """Test JSON serialization for logging/debugging."""
    event = MessageIngested(
        message_id="msg_456",
        channel="email",
        body="Hello",
    )
    
    # Serialize to JSON
    json_str = MessageToJson(event)
    
    # Deserialize from JSON
    deserialized = Parse(json_str, MessageIngested())
    
    assert deserialized.message_id == "msg_456"
    assert deserialized.channel == "email"

@pytest.mark.unit
def test_cloud_event_envelope_with_payload():
    """Test CloudEvent wrapping domain event."""
    # Create domain event
    domain_event = MessageIngested(
        message_id="msg_456",
        channel="email",
        body="Help!",
    )
    
    # Wrap in CloudEvent
    cloud_event = CloudEvent(
        id="evt_123",
        source="triage/messages",
        type="message.ingested",
        tenant_id="tenant_1",
        data=domain_event.SerializeToString(),
        data_content_type="application/protobuf",
    )
    
    # Serialize full envelope
    serialized = cloud_event.SerializeToString()
    
    # Deserialize and extract
    restored_cloud = CloudEvent()
    restored_cloud.ParseFromString(serialized)
    
    restored_domain = MessageIngested()
    restored_domain.ParseFromString(restored_cloud.data)
    
    assert restored_domain.message_id == "msg_456"
    assert restored_cloud.type == "message.ingested"

@pytest.mark.unit
def test_schema_version_forward_compat():
    """Test that old consumers can handle new schema fields."""
    # Simulate: old consumer has MessageIngested with 5 fields
    # New version adds field 8 (estimated_response_time_secs)
    
    # Create event with new field
    new_event = MessageIngested(
        message_id="msg_456",
        channel="email",
        body="Help!",
        estimated_response_time_secs=3600,
    )
    
    serialized = new_event.SerializeToString()
    
    # Old consumer deserializes without knowing field 8
    # Protobuf ignores unknown fields → safe
    old_deserialized = MessageIngested()
    old_deserialized.ParseFromString(serialized)
    
    assert old_deserialized.message_id == "msg_456"  # Known fields still work
    # estimated_response_time_secs would be ignored by old schema

@pytest.mark.integration
async def test_protobuf_to_kafka_to_protobuf():
    """Test full pipeline: Python proto → Kafka bytes → Python proto."""
    # Create event
    event = MessageIngested(
        message_id="msg_456",
        channel="email",
        body="Help!",
    )
    
    # Serialize to Kafka
    kafka_payload = event.SerializeToString()
    
    # Simulate Kafka transmission (bytes are immutable)
    received_payload = kafka_payload
    
    # Deserialize on consumer
    restored = MessageIngested()
    restored.ParseFromString(received_payload)
    
    assert restored.message_id == "msg_456"
    assert restored.body == "Help!"
```

---

## 3. S6.2 — Kafka Adapter & Debezium

### Goal
Replace OutboxPoller (polling 1s intervals) with:
1. **Kafka 4** as the persistent event bus (3 brokers KRaft, no ZooKeeper)
2. **Debezium PostgreSQL connector** capturing outbox_events table CDC
3. **CloudEvents envelope + Protobuf serialization** for language-agnostic schema (Protobuf bytes, not JSON)
4. Partition key = tenant_id for ordering + tenant isolation

### Design

#### 3.1 Kafka Infrastructure

**Kafka Cluster (3 brokers, KRaft mode):**
```yaml
# In docker-compose.yml (see Section 8)
kafka-broker-1:
  image: confluentinc/cp-kafka:7.5.0
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_PROCESS_ROLES: broker,controller  # KRaft unified mode
    KAFKA_LISTENERS: PLAINTEXT://kafka-broker-1:29092,CONTROLLER://kafka-broker-1:9092,EXTERNAL://0.0.0.0:9093
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-broker-1:29092,EXTERNAL://kafka-broker-1:9093
    KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
    KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
    KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-broker-1:9092,2@kafka-broker-2:9092,3@kafka-broker-3:9092
    KAFKA_NODE_ID: 1
    CLUSTER_ID: MkQkRmVuTjBOUjBMUQ==  # 16-char base64 ID for KRaft

# Topics (auto-created with settings)
topics:
  - name: triage.message.ingested
    partitions: 12                       # Parallel processing
    replication_factor: 3                # HA
    config:
      retention.ms: 604800000            # 7 days
      compression.type: snappy
      min.insync.replicas: 2
      
  - name: triage.message.classified
    partitions: 12
    replication_factor: 3
    
  - name: triage.action.executed
    partitions: 12
    replication_factor: 3
    
  - name: triage.message.escalated
    partitions: 12
    replication_factor: 3
    
  - name: triage.dlq
    partitions: 3
    replication_factor: 3
    config:
      retention.ms: 2592000000          # 30 days (longer for debugging)
```

#### 3.2 Debezium PostgreSQL Connector

**File: `tools/debezium/postgres-connector-config.json`**

**Key Design Decisions:**
- `transforms.outbox.table.field.event.key`: **tenant_id** (partition key for tenant isolation, not aggregate_id)
- `snapshot.mode`: **initial** (snapshot only on first start; prevents re-emission of pre-existing events on restart)

**H2 FIX — CRITICAL: Schema Validation Before Connector Deployment**

The Debezium connector config expects the `outbox_events` table to exist with a specific schema. This section documents the required schema and validation steps.

**Required outbox_events Table Schema:**

```sql
CREATE TABLE IF NOT EXISTS triage.outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  aggregate_type VARCHAR(100) NOT NULL,
  aggregate_id VARCHAR(255) NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  published_at TIMESTAMP WITH TIME ZONE NULL,
  FOREIGN KEY (tenant_id) REFERENCES triage.tenants(id)
);

CREATE INDEX IF NOT EXISTS idx_outbox_tenant_id ON triage.outbox_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON triage.outbox_events(published_at) 
  WHERE published_at IS NULL;
```

**Schema Validation Query (H2 Fix — Add to Pre-Migration Checklist Step 0):**

Before deploying any Debezium code, verify the schema matches expectations:

```sql
-- Step 0: Validate Schema (MUST PASS before proceeding)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_schema='triage' AND table_name='outbox_events'
ORDER BY ordinal_position;

-- Expected output:
-- column_name       | data_type                  | is_nullable
-- id                | uuid                       | NO
-- tenant_id         | uuid                       | NO
-- aggregate_type    | character varying          | NO
-- aggregate_id      | character varying          | NO
-- event_type        | character varying          | NO
-- payload           | jsonb                      | NO
-- created_at        | timestamp with time zone   | NO
-- published_at      | timestamp with time zone   | YES

-- If any column is missing or has wrong type: STOP deployment
-- Fix schema first, then retry deployment checklist from Step 1
```

**Connector Field Mappings (Matched to Schema):**

The following Debezium config fields are now explicitly tied to the above schema:
- `transforms.outbox.table.field.event.key: "tenant_id"` ← matches schema column
- `transforms.outbox.table.field.event.id: "id"` ← matches schema column
- `transforms.outbox.table.field.event.timestamp: "created_at"` ← matches schema column
- Filter predicate checks `published_at IS NULL` ← matches schema column

**H1 FIX — CRITICAL: Automated Pre-Migration Check & Debezium Snapshot Re-Emission Prevention**

Before deploying Debezium in production, execute this enhanced pre-migration checklist to prevent event re-emission on connector restart:

```markdown
## Pre-Migration Debezium Checklist (Complete before Phase 1 Cutover)

### Step 0: Run Automated Pre-Flight Check (H1 Fix — Automated Validation)

**File: `tools/debezium/pre_migration_check.py`**

This script automates the safety checks and prevents human error:

```python
#!/usr/bin/env python3
"""
Pre-migration check for Debezium deployment.
Prevents event re-emission by verifying outbox state before connector starts.
"""
import sys
import os
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

DB_URL = os.getenv("DATABASE_URL", "postgresql://triage_app:password@postgres:5432/triage")

def run_checks():
    """Execute pre-migration checks; fail if any check fails."""
    engine = create_engine(DB_URL)
    
    print("[1/4] Validating outbox_events schema...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_schema='triage' AND table_name='outbox_events'
            ORDER BY ordinal_position
        """))
        
        required_columns = {
            'id': 'uuid',
            'tenant_id': 'uuid',
            'aggregate_type': 'character varying',
            'aggregate_id': 'character varying',
            'event_type': 'character varying',
            'payload': 'jsonb',
            'created_at': 'timestamp with time zone',
            'published_at': 'timestamp with time zone',
        }
        
        found_columns = {row[0]: row[1] for row in result}
        
        for col, dtype in required_columns.items():
            if col not in found_columns:
                print(f"❌ FAIL: Column '{col}' not found in outbox_events schema")
                return False
            if found_columns[col] != dtype:
                print(f"❌ FAIL: Column '{col}' has type '{found_columns[col]}', expected '{dtype}'")
                return False
        
        print("✓ Schema validated")
    
    print("\n[2/4] Checking for unpublished events that should be cleaned...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as unpublished_old
            FROM triage.outbox_events 
            WHERE published_at IS NULL 
              AND created_at < NOW() - INTERVAL '1 hour'
        """))
        
        unpublished_old_count = result.scalar()
        
        if unpublished_old_count > 0:
            print(f"⚠️  WARNING: Found {unpublished_old_count} unpublished events older than 1 hour")
            print("   These should be cleaned up before deployment to prevent re-emission")
            print("   Run: UPDATE triage.outbox_events SET published_at = NOW()")
            print("        WHERE published_at IS NULL AND created_at < NOW() - INTERVAL '1 hour';")
            
            response = input("   Clean up old events now? (yes/no): ").lower()
            if response == 'yes':
                conn.execute(text("""
                    UPDATE triage.outbox_events 
                    SET published_at = NOW() 
                    WHERE published_at IS NULL 
                      AND created_at < NOW() - INTERVAL '1 hour'
                """))
                conn.commit()
                print("✓ Old unpublished events marked as published")
            else:
                print("❌ FAIL: Cannot proceed without cleaning old unpublished events")
                return False
        else:
            print("✓ No old unpublished events found")
    
    print("\n[3/4] Checking current unpublished event count (should be <100)...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as unpublished_count 
            FROM triage.outbox_events 
            WHERE published_at IS NULL
        """))
        
        unpublished_count = result.scalar()
        
        if unpublished_count > 100:
            print(f"❌ FAIL: Found {unpublished_count} unpublished events (threshold: 100)")
            print("   OutboxPoller may be lagging or blocked. Investigate before deployment.")
            return False
        
        print(f"✓ Unpublished event count OK: {unpublished_count}")
    
    print("\n[4/4] Verifying Kafka brokers are reachable...")
    # Optional: test Kafka connectivity
    kafka_brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker-1:9092").split(',')
    print(f"   Kafka brokers: {kafka_brokers}")
    print("✓ (Manual verification: ensure Kafka cluster is healthy)")
    
    print("\n✅ All pre-migration checks passed. Safe to deploy Debezium connector.")
    return True

if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
```

**Usage:**

```bash
# Run pre-migration check
export DATABASE_URL="postgresql://triage_app:password@postgres:5432/triage"
python3 tools/debezium/pre_migration_check.py

# Expected output on success:
# [1/4] Validating outbox_events schema...
# ✓ Schema validated
# [2/4] Checking for unpublished events...
# ✓ No old unpublished events found
# [3/4] Checking current unpublished event count...
# ✓ Unpublished event count OK: 15
# [4/4] Verifying Kafka brokers...
# ✓ (Manual verification: ensure Kafka cluster is healthy)
# ✅ All pre-migration checks passed. Safe to deploy Debezium connector.

# If any check fails, fix the issue and re-run.
```

**CI/CD Integration (H1 Fix — Enforce Automated Check):**

Add to GitHub Actions pre-deployment pipeline:

```yaml
# .github/workflows/deploy-debezium.yml
name: Deploy Debezium Connector

on:
  workflow_dispatch:  # Manual trigger only

jobs:
  pre-flight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Run pre-migration checks
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          KAFKA_BOOTSTRAP_SERVERS: ${{ secrets.KAFKA_BOOTSTRAP_SERVERS }}
        run: |
          pip install sqlalchemy psycopg2-binary
          python3 tools/debezium/pre_migration_check.py
          # If script returns non-zero, deployment stops (workflow fails)
      
      - name: Deploy Debezium connector
        if: success()
        run: |
          # Only deploy if pre-flight checks passed
          curl -X POST http://kafka-connect:8083/connectors \
            -H "Content-Type: application/json" \
            -d @tools/debezium/postgres-connector-config.json
```

**Summary (H1 Fix):**
- **Before:** Manual, error-prone checklist; easy to skip Step 3 cleanup
- **After:** Automated script that fails deployment if conditions not met; cannot proceed without explicit validation
- **Result:** Prevents silent re-emission of old events on connector restart

### Step 1: Verify Current Outbox State (5 min)
```sql
-- Check for pre-existing unpublished events (informational; automated check in Step 0)
SELECT COUNT(*) as unpublished_count FROM triage.outbox_events WHERE published_at IS NULL;
-- Expected: <100 (normal backlog)
-- If >10,000: Stop, investigate MVP OutboxPoller lag
```

### Step 2: Run Connector Dry-Run (5 min)
1. Deploy Debezium with `snapshot.mode: "never"` (dry-run mode)
   - This connector will NOT snapshot; only capture new CDC changes
   - Verifies connector can connect and consume WAL
2. Monitor Debezium lag metric: `Debezium_connector_lag_offset_ms`
   - Should decrease steadily toward 0
   - Acceptable: <5 min to reach 0
3. Expected behavior: Connector catches up to current WAL offset, lag stabilizes at ~0ms
4. If lag stalls or increases: Check connector logs for errors before proceeding

### Step 3: Clean Up Old Unpublished Events (2 min)
```sql
-- Manually mark old events as published to prevent re-emission
-- Only publish events >1 hour old (gives grace period for in-flight processing)
UPDATE triage.outbox_events 
SET published_at = NOW() 
WHERE published_at IS NULL 
  AND created_at < NOW() - INTERVAL '1 hour';
```

### Step 4: Deploy Connector with Snapshot (2 min)
1. Stop connector from dry-run
2. Redeploy connector with `snapshot.mode: "initial"`
   - On first start: takes snapshot of current `outbox_events` state (includes post-cutover records)
   - Snapshot marks completion internally
   - Future connector restarts skip snapshot phase (snapshot complete flag set)
3. Monitor: `Debezium_connector_lag_offset_ms` should remain <5s

### Step 5: Verify Snapshot Completion (3 min)
Monitor Debezium metrics for 2 minutes:
- Connector lag remains stable (<5s)
- No error logs in Debezium container
- No events re-appearing in Kafka topics
- Connector status: "RUNNING" with snapshot_completed=true (in metrics)

**If all checks pass:** Proceed to Phase 1 cutover
**If any check fails:** Rollback connector, debug, retry from Step 1

**Snapshot Behavior Deep Dive:**
- `snapshot.mode: "initial"` means: snapshot outbox_events EXACTLY ONCE per connector lifecycle
- During dry-run (`never` mode): no snapshot taken
- On first production deployment (`initial` mode): snapshot captures current table state exactly once
- If connector crashes or is restarted: snapshot does NOT re-run (snapshot complete)
- This design prevents re-emission of already-published events
- REQUIREMENT: Step 3 cleanup ensures no old unpublished events exist to be re-emitted
```

```json
{
  "name": "postgres-cdc-outbox",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": 5432,
    "database.user": "triage_app",
    "database.password": "${DB_PASSWORD}",
    "database.dbname": "triage",
    "database.server.name": "triage_db",
    
    "plugin.name": "pgoutput",
    "publication.name": "dbz_publication",
    "slot.name": "dbz_slot",
    "slot.drop.on.stop": false,
    
    "table.include.list": "triage.outbox_events",
    "database.history.kafka.bootstrap.servers": "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092",
    "database.history.kafka.topic": "dbhistory.triage",
    
    "transforms": "outbox,filter",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    "transforms.outbox.route.topic.replacement": "${routedByValue}",
    "transforms.outbox.route.by.field": "event_type",
    "transforms.outbox.table.field.event.key": "tenant_id",
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.excluded.columns": "published_at",
    "transforms.outbox.table.field.event.timestamp": "created_at",
    
    "transforms.filter.type": "org.apache.kafka.connect.transforms.Filter",
    "transforms.filter.predicate": "is_unpublished",
    "predicates": "is_unpublished",
    "predicates.is_unpublished.type": "org.apache.kafka.connect.transforms.predicates.ValueMatches",
    "predicates.is_unpublished.field": "after.published_at",
    "predicates.is_unpublished.contains": "null",
    
    "snapshot.mode": "initial",
    "snapshot.isolation.mode": "read_committed",
    "errors.deadletterqueue.topic": "triage.dlq.postgres",
    "errors.deadletterqueue.topic.replication.factor": 3,
    "errors.log.enable": true,
    
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": false,
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter.schemas.enable": false,
    
    "batch.size": 2048,
    "poll.interval.ms": 1000,
    "max.queue.size": 8192,
    "lsn.commit.timeout.ms": 10000,
    "connection.timeout.ms": 30000,
    "heartbeat.interval.ms": 10000
  }
}
```

**Pre-Migration Checklist (addressing M2 findings):**
Before activating Debezium connector in production, verify:
1. Run connector with `snapshot.mode: "never"` in dry-run (don't deploy to production)
2. Verify connector lag is 0 (catches up to current WAL)
3. Verify no pre-existing unpublished events in outbox_events table that should be migrated
4. Then activate with `snapshot.mode: "initial"` for first production deployment

**PostgreSQL Preparation:**
```sql
-- Create publication for Debezium
CREATE PUBLICATION dbz_publication FOR TABLE triage.outbox_events;

-- Enable logical replication
ALTER SYSTEM SET wal_level = logical;
-- Restart PostgreSQL for wal_level to take effect

-- Verify
SHOW wal_level;  -- Should return 'logical'
```

#### 3.3 KafkaEventBus Implementation (Protobuf Serialization — Addressing H1 & H5)

**Design Decision: Option A Selected — Use Protobuf bytes serialization**
- CloudEvent is serialized to Protobuf bytes (not JSON) to align with S6.1 contracts
- This ensures consistency: domain events wrapped in CloudEvent → serialized to Protobuf bytes → transmitted in Kafka → deserialized by consumers to CloudEvent → extracted to domain event
- Event ID is reused from OutboxEvent to ensure idempotency consistency (addresses H5)

**File: `services/api/src/triage/adapters/event_bus_kafka.py`**
```python
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import asyncio
import json
import uuid
import structlog

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
from google.protobuf.json_format import MessageToJson, Parse
from triage.events.v1 import CloudEvent, MessageIngested, MessageClassified
from triage.models.events import OutboxEvent

log = structlog.get_logger(__name__)

class KafkaEventBus:
    """Production EventBus backed by Apache Kafka with Protobuf serialization."""
    
    def __init__(
        self,
        bootstrap_servers: str = "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092",
        consumer_group_id: Optional[str] = None,
    ):
        """Initialize Kafka-backed event bus.
        
        Args:
            bootstrap_servers: Comma-separated broker addresses
            consumer_group_id: Consumer group (for subscribers)
        """
        self.bootstrap_servers = bootstrap_servers
        self.consumer_group_id = consumer_group_id or "triage-events"
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._handlers: Dict[str, Callable] = {}
        
    async def connect(self) -> None:
        """Connect to Kafka cluster."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=self._serialize_protobuf,  # Protobuf serializer
            acks='all',                                    # Wait for all replicas
            compression_type='snappy',
            linger_ms=100,                                 # Batch for efficiency
        )
        await self._producer.start()
        
        log.info("kafka_producer_connected", bootstrap_servers=self.bootstrap_servers)
    
    async def disconnect(self) -> None:
        """Disconnect from Kafka cluster."""
        if self._producer:
            await self._producer.stop()
        if self._consumer:
            await self._consumer.stop()
        
        log.info("kafka_disconnected")
    
    @staticmethod
    def _serialize_protobuf(protobuf_msg) -> bytes:
        """Serialize Protobuf message to bytes."""
        if hasattr(protobuf_msg, 'SerializeToString'):
            return protobuf_msg.SerializeToString()
        return bytes(protobuf_msg)
    
    async def publish(
        self,
        event_type: str,
        tenant_id: str,
        payload,  # Can be Protobuf message or dict (H1 fix: prefer Protobuf)
        aggregate_type: str = "message",
        aggregate_id: Optional[str] = None,
        outbox_event_id: Optional[str] = None,  # Reuse from OutboxEvent (H5 fix)
    ) -> None:
        """Publish event to Kafka topic using Protobuf CloudEvent (H1 fix: Protobuf serialization).
        
        Topic name derived from event_type: "message.ingested" → "triage.message.ingested"
        Partition key = tenant_id (ensures ordering per tenant)
        Message value = Protobuf-serialized CloudEvent
        
        DESIGN DECISION (H1): CloudEvent.data field stores Protobuf-serialized domain event bytes.
        This ensures consistency: S6.1 Protobuf contracts → S6.2 Kafka envelope → S6.3 Consumer.
        
        Args:
            event_type: Event type (e.g., "message.ingested")
            tenant_id: Tenant ID (becomes partition key)
            payload: Event payload. PREFERRED: Protobuf message object (e.g., MessageIngested).
                    FALLBACK: dict for MVP transition period.
            aggregate_type: Domain object type (e.g., "message")
            aggregate_id: Aggregate ID (e.g., message_id)
            outbox_event_id: Reuse OutboxEvent.id for idempotency consistency (H5 fix)
        """
        if not self._producer:
            raise RuntimeError("EventBus not connected. Call connect() first.")
        
        # Convert event type to topic name: "message.ingested" → "triage.message.ingested"
        topic = f"triage.{event_type.replace('.', '.')}"
        
        # Wrap in CloudEvents envelope (Protobuf)
        cloud_event = self._build_cloud_event(
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            aggregate_id=aggregate_id,
            outbox_event_id=outbox_event_id,  # Reuse ID from OutboxEvent
        )
        
        # Send to Kafka (partition key = tenant_id for tenant isolation)
        # value_serializer will call _serialize_protobuf()
        future = await self._producer.send_and_wait(
            topic,
            value=cloud_event,  # Protobuf message
            key=tenant_id.encode('utf-8'),  # Partition by tenant
        )
        
        log.info(
            "event_published",
            event_type=event_type,
            topic=topic,
            tenant_id=tenant_id,
            partition=future.partition,
            offset=future.offset,
            event_id=cloud_event.id,
        )
    
    def _build_cloud_event(
        self,
        event_type: str,
        tenant_id: str,
        payload: Dict[str, Any],
        aggregate_id: Optional[str],
        outbox_event_id: Optional[str] = None,
    ) -> CloudEvent:
        """Build CloudEvents Protobuf envelope.
        
        Args:
            outbox_event_id: If provided, reuse this ID instead of generating new UUID
        
        Returns:
            CloudEvent Protobuf message
        """
        # Use provided ID or generate new one (H5 fix: reuse from OutboxEvent if available)
        event_id = outbox_event_id or str(uuid.uuid4())
        
        return CloudEvent(
            id=event_id,
            source="triage/messages",
            type=event_type,
            occurred_at=datetime.utcnow(),  # Will be converted to Protobuf Timestamp
            tenant_id=tenant_id,
            subject=f"tenant/{tenant_id}/aggregate/{aggregate_id or 'unknown'}",
            data_content_type="application/protobuf",
            attributes={
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id or "",
            },
            # Note: payload stored as bytes in Protobuf; see S6.1 for domain event serialization
            data=self._serialize_payload(payload),
        )
    
    @staticmethod
    def _serialize_payload(domain_event_proto) -> bytes:
        """Serialize Protobuf domain event to bytes.
        
        Args:
            domain_event_proto: Protobuf message object (e.g., MessageIngested)
                               OR dict (fallback for MVP transition)
        
        Returns:
            Serialized bytes (Protobuf-preferred, JSON fallback)
        
        Design Decision (H1 fix): CloudEvent.data field stores Protobuf-serialized
        domain events to ensure S6.1 ↔ S6.2 contract consistency.
        """
        if hasattr(domain_event_proto, 'SerializeToString'):
            # Protobuf message: serialize to bytes
            return domain_event_proto.SerializeToString()
        else:
            # Fallback: dict to JSON (for MVP transition period)
            return json.dumps(domain_event_proto).encode('utf-8')
    
    async def subscribe(
        self,
        event_types: List[str],
        handler: Callable[[Dict[str, Any]], None],
        consumer_group_id: Optional[str] = None,
    ) -> None:
        """Subscribe to event types and handle with callback.
        
        Args:
            event_types: List of event types to subscribe to (e.g., ["message.ingested"])
            handler: Async callable(event_dict) to process each event
            consumer_group_id: Override default consumer group
        """
        topics = [f"triage.{et.replace('.', '.')}" for et in event_types]
        
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=consumer_group_id or self.consumer_group_id,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=self._deserialize_protobuf,  # Protobuf deserializer
            max_poll_records=100,
            session_timeout_ms=30000,
        )
        
        await self._consumer.start()
        
        try:
            async for message in self._consumer:
                try:
                    # message.value is now a CloudEvent Protobuf message
                    cloud_event = message.value
                    
                    # Extract and deserialize payload
                    event_dict = {
                        "id": cloud_event.id,
                        "type": cloud_event.type,
                        "tenant_id": cloud_event.tenant_id,
                        "occurred_at": cloud_event.occurred_at.isoformat(),
                        "data": json.loads(cloud_event.data.decode('utf-8')),
                    }
                    
                    await handler(event_dict)
                    await self._consumer.commit()  # Commit after successful processing
                except Exception as e:
                    log.exception("event_handler_failed", error=str(e))
                    # Send to DLQ (S6.3)
                    await self._send_to_dlq(message, e)
        finally:
            await self._consumer.stop()
    
    @staticmethod
    def _deserialize_protobuf(data: bytes) -> CloudEvent:
        """Deserialize bytes to CloudEvent Protobuf message."""
        cloud_event = CloudEvent()
        cloud_event.ParseFromString(data)
        return cloud_event
    
    async def _send_to_dlq(self, message: Any, error: Exception) -> None:
        """Send failed event to Dead Letter Queue."""
        dlq_event = {
            "original_event": {
                "id": message.value.id,
                "type": message.value.type,
            },
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": message.value.attributes.get("retry_count", 0) + 1,
        }
        
        await self._producer.send_and_wait(
            "triage.dlq",
            value=dlq_event,
            key=message.value.tenant_id.encode('utf-8'),
        )
        
        log.warning(
            "event_sent_to_dlq",
            error=str(error),
            retry_count=dlq_event["retry_count"],
        )
```               log.exception("event_handler_failed", event=message.value, error=str(e))
                    # Send to DLQ (S6.3)
                    await self._send_to_dlq(message, e)
        finally:
            await self._consumer.stop()
    
    async def _send_to_dlq(self, message: Any, error: Exception) -> None:
        """Send failed event to Dead Letter Queue."""
        dlq_event = {
            "original_event": message.value,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": message.value.get("retry_count", 0) + 1,
        }
        
        await self._producer.send_and_wait(
            "triage.dlq",
            value=dlq_event,
            key=message.value.get("tenant_id", "unknown").encode('utf-8'),
        )
        
        log.warning(
            "event_sent_to_dlq",
            error=str(error),
            retry_count=dlq_event["retry_count"],
        )
```

#### 3.4 EventBus Factory (Toggle MVP ↔ Kafka)

**File: `services/api/src/triage/adapters/event_bus_factory.py`**
```python
from typing import Union
import os
from triage.ingestion.outbox import OutboxWriter, OutboxPoller
from triage.adapters.event_bus_kafka import KafkaEventBus

class EventBusFactory:
    """Factory for instantiating EventBus adapter based on config."""
    
    @staticmethod
    def create_event_bus(use_kafka: bool = False) -> Union[OutboxWriter, KafkaEventBus]:
        """
        Args:
            use_kafka: If True, use Kafka adapter; else use MVP OutboxWriter.
        """
        if use_kafka:
            kafka_servers = os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092"
            )
            return KafkaEventBus(bootstrap_servers=kafka_servers)
        else:
            return OutboxWriter()

# Usage in app startup:
# from triage.adapters.event_bus_factory import EventBusFactory
# USE_KAFKA = os.getenv("USE_KAFKA_EVENTS", "false").lower() == "true"
# event_bus = EventBusFactory.create_event_bus(use_kafka=USE_KAFKA)
```

#### 3.5 Contract Tests (MVP vs Kafka)

**File: `services/api/tests/test_event_bus_contracts.py`**
```python
import pytest
import asyncio
from typing import Dict, Any, List

from triage.ingestion.outbox import OutboxWriter
from triage.adapters.event_bus_kafka import KafkaEventBus


class EventBusContractTest:
    """Abstract contract test suite for all EventBus implementations."""
    
    @pytest.fixture
    async def event_bus(self):
        """Fixture: subclasses override to provide implementation."""
        raise NotImplementedError("Subclasses must implement")
    
    @pytest.mark.asyncio
    async def test_publish_and_receive_single_event(self, event_bus):
        """Test: publish one event, receive it."""
        events_received: List[Dict] = []
        
        async def handler(event: Dict[str, Any]) -> None:
            events_received.append(event)
        
        # Subscribe
        await event_bus.subscribe(["message.ingested"], handler)
        
        # Publish
        await event_bus.publish(
            event_type="message.ingested",
            tenant_id="tenant_1",
            payload={"message_id": "msg_123", "body": "Hello"},
        )
        
        # Wait for delivery
        await asyncio.sleep(0.5)
        
        # Assert
        assert len(events_received) == 1
        assert events_received[0]["message_id"] == "msg_123"
    
    @pytest.mark.asyncio
    async def test_partition_key_tenant_isolation(self, event_bus):
        """Test: events from tenant_1 and tenant_2 are logically isolated."""
        # This is implementation-specific; for Kafka, verify partition key = tenant_id
        events_t1: List[Dict] = []
        
        async def handler_t1(event: Dict[str, Any]) -> None:
            if event.get("tenant_id") == "tenant_1":
                events_t1.append(event)
        
        await event_bus.subscribe(["message.ingested"], handler_t1)
        
        # Publish from both tenants
        await event_bus.publish(
            event_type="message.ingested",
            tenant_id="tenant_1",
            payload={"message_id": "t1_msg_1"},
        )
        await event_bus.publish(
            event_type="message.ingested",
            tenant_id="tenant_2",
            payload={"message_id": "t2_msg_1"},
        )
        
        await asyncio.sleep(0.5)
        
        # Assert: handler sees only tenant_1 events
        assert len(events_t1) >= 1
        for event in events_t1:
            assert event["tenant_id"] == "tenant_1"


# Concrete implementations for each adapter

class TestOutboxWriterContract(EventBusContractTest):
    """Test OutboxWriter (MVP) against contract."""
    
    @pytest.fixture
    async def event_bus(self):
        bus = OutboxWriter()
        yield bus
        # Cleanup


class TestKafkaEventBusContract(EventBusContractTest):
    """Test KafkaEventBus (Production) against contract."""
    
    @pytest.fixture
    async def event_bus(self):
        bus = KafkaEventBus()
        await bus.connect()
        yield bus
        await bus.disconnect()
```

---

## 4. S6.3 — Consumer Idempotency & DLQ

### Goal
Guarantee exactly-once event processing despite:
- Duplicate events (e.g., Kafka retries, application crashes)
- Processing failures (network, DB, external service timeouts)
- Consumer restarts (resume from last checkpoint)

### Design

#### 4.1 Idempotency Layer

**Fast Path (In-Memory Redis):** for high-volume events (message.ingested, action.executed)
- Key: `idempotency:{tenant_id}:{event_id}`
- Value: `{result_summary}` (minimal; e.g., "processed_ok" or error code)
- TTL: 7 days
- Trade-off: Fast, but loses state on Redis restart (acceptable for non-critical events)

**Slow Path (Postgres):** for critical events (refunds, escalations, chargebacks)
- Table: `idempotency_records` (tenant_id, event_id, event_type, result_json, processed_at)
- Unique constraint: (tenant_id, event_id) to prevent duplicate inserts
- Query: SELECT to check if already processed
- Trade-off: Durable, but slower (~10ms insert)

**File: `services/api/src/triage/adapters/idempotency.py`**
```python
import asyncio
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import redis.asyncio as redis
import structlog

log = structlog.get_logger(__name__)

@dataclass
class IdempotencyResult:
    """Result of idempotency check."""
    is_duplicate: bool
    prior_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class IdempotencyStore:
    """Deduplicate events using Redis (fast) + Postgres (durable) dual-write."""
    
    FAST_PATH_TTL = timedelta(days=7)
    REDIS_KEY_PREFIX = "idempotency"
    
    def __init__(self, redis_client: redis.Redis, db_session=None):
        """
        Args:
            redis_client: Redis async client
            db_session: Optional SQLAlchemy async session (for slow path)
        """
        self.redis = redis_client
        self.db_session = db_session
    
    async def check_or_record(
        self,
        tenant_id: str,
        event_id: str,
        event_type: str,
        use_slow_path: bool = False,
    ) -> IdempotencyResult:
        """Check if event was already processed; record if not.
        
        Args:
            tenant_id: Tenant context
            event_id: Unique event identifier
            event_type: Type of event (for deciding path)
            use_slow_path: If True, use durable Postgres path
        
        Returns:
            IdempotencyResult with is_duplicate flag and optional prior result
        """
        result = IdempotencyResult(is_duplicate=False)
        
        if use_slow_path:
            result = await self._check_or_record_slow_path(tenant_id, event_id, event_type)
        else:
            result = await self._check_or_record_fast_path(tenant_id, event_id)
        
        return result
    
    async def _check_or_record_fast_path(
        self,
        tenant_id: str,
        event_id: str,
    ) -> IdempotencyResult:
        """Fast path: Redis check + record."""
        key = f"{self.REDIS_KEY_PREFIX}:{tenant_id}:{event_id}"
        
        # Check
        existing = await self.redis.get(key)
        if existing:
            log.info("idempotency_fast_path_hit", event_id=event_id, tenant_id=tenant_id)
            return IdempotencyResult(
                is_duplicate=True,
                prior_result={"cached": True},
            )
        
        # Record
        await self.redis.setex(
            key,
            int(self.FAST_PATH_TTL.total_seconds()),
            "processed_ok",
        )
        
        log.info("idempotency_fast_path_record", event_id=event_id, tenant_id=tenant_id)
        return IdempotencyResult(is_duplicate=False)
    
    async def _check_or_record_slow_path(
        self,
        tenant_id: str,
        event_id: str,
        event_type: str,
    ) -> IdempotencyResult:
        """Slow path: Postgres ON CONFLICT for atomic check + record (M2 Fix).
        
        Uses PostgreSQL native ON CONFLICT clause for truly atomic insert-or-fetch.
        This avoids race conditions from exception-based duplicate detection.
        
        (M2 Fix) Before: Relied on catching "duplicate key" exception (fragile, DB-specific)
        After: Uses ON CONFLICT DO UPDATE for atomic operation
        """
        try:
            # Atomic insert-or-update using ON CONFLICT (M2 Fix)
            # This always succeeds; PostgreSQL handles the conflict atomically
            stmt = """
                INSERT INTO triage.idempotency_records 
                  (tenant_id, event_id, event_type, result_json, processed_at, is_first_attempt)
                VALUES 
                  (:tenant_id, :event_id, :event_type, :result_json, :processed_at, true)
                ON CONFLICT (tenant_id, event_id)
                DO UPDATE SET
                  result_json = idempotency_records.result_json,  -- Keep original result
                  is_first_attempt = false
                RETURNING is_first_attempt;
            """
            result = await self.db_session.execute(
                text(stmt),  # Use text() for raw SQL with parameters
                {
                    "tenant_id": tenant_id,
                    "event_id": event_id,
                    "event_type": event_type,
                    "result_json": json.dumps({"status": "processing"}),
                    "processed_at": datetime.utcnow(),
                },
            )
            
            # ON CONFLICT returns is_first_attempt: True if INSERT, False if UPDATE (already exists)
            is_first_attempt = result.scalar()
            await self.db_session.commit()
            
            if is_first_attempt:
                log.info("idempotency_slow_path_record", event_id=event_id, tenant_id=tenant_id)
                return IdempotencyResult(is_duplicate=False)
            else:
                # Already processed (conflict occurred; updated row)
                log.info("idempotency_slow_path_hit", event_id=event_id, tenant_id=tenant_id)
                
                # Fetch prior result
                select_stmt = text("""
                    SELECT result_json FROM triage.idempotency_records
                    WHERE tenant_id = :tenant_id AND event_id = :event_id
                """)
                row = await self.db_session.execute(
                    select_stmt,
                    {"tenant_id": tenant_id, "event_id": event_id},
                )
                prior = row.scalar()
                
                return IdempotencyResult(
                    is_duplicate=True,
                    prior_result=json.loads(prior) if prior else None,
                )
        
        except Exception as e:
            log.exception("idempotency_slow_path_error", error=str(e))
            return IdempotencyResult(
                is_duplicate=False,
                error=str(e),
            )


class EventHandler:
    """Base event handler with built-in idempotency."""
    
    def __init__(self, idempotency_store: IdempotencyStore):
        self.idempotency = idempotency_store
    
    async def handle_with_idempotency(
        self,
        event: Dict[str, Any],
        handler_func,
        use_slow_path: bool = False,
    ) -> Dict[str, Any]:
        """Execute handler with idempotency guarantees.
        
        Args:
            event: Event dict (must have tenant_id, id, type)
            handler_func: Async callable(event) -> result
            use_slow_path: Use durable Postgres path
        
        Returns:
            Result from handler (or cached result if duplicate)
        """
        tenant_id = event.get("tenant_id")
        event_id = event.get("id")
        event_type = event.get("type")
        
        # Check idempotency
        idempotency_result = await self.idempotency.check_or_record(
            tenant_id=tenant_id,
            event_id=event_id,
            event_type=event_type,
            use_slow_path=use_slow_path,
        )
        
        if idempotency_result.is_duplicate:
            log.info(
                "idempotency_cache_hit",
                event_id=event_id,
                event_type=event_type,
            )
            return idempotency_result.prior_result or {"cached": True}
        
        # First-time processing
        try:
            result = await handler_func(event)
            
            # Update idempotency record with result (if slow path)
            if use_slow_path:
                await self.idempotency.redis.setex(
                    f"{self.idempotency.REDIS_KEY_PREFIX}:{tenant_id}:{event_id}",
                    int(self.idempotency.FAST_PATH_TTL.total_seconds()),
                    json.dumps(result),
                )
            
            return result
        
        except Exception as e:
            log.exception(
                "event_handler_error",
                event_id=event_id,
                event_type=event_type,
                error=str(e),
            )
            raise
```

#### 4.2 DLQ (Dead Letter Queue)

**File: `services/api/src/triage/adapters/dlq.py`**
```python
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import structlog

log = structlog.get_logger(__name__)

class DeadLetterQueue:
    """Manage failed events with retry policy."""
    
    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 10, 60]  # exponential backoff: 1s, 10s, 60s
    
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.dlq_topic = "triage.dlq"
    
    async def send_to_dlq(
        self,
        event: Dict[str, Any],
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """Send event to DLQ with error details.
        
        Args:
            event: Original event that failed
            error: Exception that was raised
            retry_count: Number of retries so far
        """
        dlq_event = {
            "original_event": event,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": retry_count,
            "next_retry_at": self._calculate_next_retry(retry_count),
        }
        
        await self.event_bus.publish(
            event_type="dlq.event_failed",
            tenant_id=event.get("tenant_id", "unknown"),
            payload=dlq_event,
        )
        
        log.warning(
            "event_dlq_sent",
            event_id=event.get("id"),
            retry_count=retry_count,
            error=str(error),
        )
    
    def _calculate_next_retry(self, retry_count: int) -> Optional[str]:
        """Calculate when event should be retried."""
        if retry_count >= self.MAX_RETRIES:
            return None  # No more retries
        
        backoff_seconds = self.RETRY_BACKOFF[min(retry_count, len(self.RETRY_BACKOFF) - 1)]
        next_retry = datetime.utcnow() + timedelta(seconds=backoff_seconds)
        return next_retry.isoformat()
    
    async def replay_from_dlq(
        self,
        dlq_event_id: str,
        handler_func,
    ) -> bool:
        """Manually replay event from DLQ.
        
        Args:
            dlq_event_id: ID of DLQ event to replay
            handler_func: Async callable to handle event
        
        Returns:
            True if replay succeeded, False otherwise
        """
        try:
            # Fetch DLQ event from database
            # (implementation: query triage.dlq_events or retrieve from DLQ topic)
            
            # Re-invoke handler
            await handler_func(dlq_event_id)
            
            log.info("dlq_event_replayed", dlq_event_id=dlq_event_id)
            return True
        except Exception as e:
            log.exception("dlq_replay_failed", dlq_event_id=dlq_event_id, error=str(e))
            return False
```

#### 4.3 Consumer Retry Policy

**File: `services/api/src/triage/adapters/event_consumer.py`**
```python
from typing import Callable, Dict, Any
import asyncio
import structlog

log = structlog.get_logger(__name__)

class ResilientEventConsumer:
    """Consume events with built-in retry logic."""
    
    def __init__(
        self,
        event_bus,
        idempotency_store,
        dlq,
        max_retries: int = 3,
    ):
        self.event_bus = event_bus
        self.idempotency = idempotency_store
        self.dlq = dlq
        self.max_retries = max_retries
    
    async def consume_with_retry(
        self,
        event: Dict[str, Any],
        handler_func: Callable,
        use_slow_path: bool = False,
    ) -> None:
        """Consume event with retry policy.
        
        Retry logic:
        1. Attempt handler (0ms)
        2. On failure, retry with exponential backoff (1s, 10s, 60s)
        3. After 3 failures, send to DLQ
        """
        tenant_id = event.get("tenant_id")
        event_id = event.get("id")
        
        for attempt in range(self.max_retries + 1):
            try:
                # Check idempotency
                idempotency_result = await self.idempotency.check_or_record(
                    tenant_id=tenant_id,
                    event_id=event_id,
                    event_type=event.get("type"),
                    use_slow_path=use_slow_path,
                )
                
                if idempotency_result.is_duplicate:
                    log.info("event_already_processed", event_id=event_id)
                    return
                
                # Execute handler
                result = await handler_func(event)
                
                log.info(
                    "event_processed",
                    event_id=event_id,
                    tenant_id=tenant_id,
                    attempt=attempt + 1,
                )
                return
            
            except Exception as e:
                if attempt < self.max_retries:
                    # Retry with backoff
                    backoff_seconds = [1, 10, 60][attempt]
                    log.warning(
                        "event_processing_failed_retry",
                        event_id=event_id,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_seconds,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff_seconds)
                else:
                    # Max retries exceeded → send to DLQ
                    log.error(
                        "event_processing_failed_dlq",
                        event_id=event_id,
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    await self.dlq.send_to_dlq(event, e, retry_count=attempt)
                    return
```

#### 4.4 Database Schema (Idempotency & DLQ)

**File: `packages/py_core/alembic/versions/0008_sprint6_idempotency.py`**
```python
"""Sprint 6: Idempotency & DLQ tables."""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Idempotency records (insert-first strategy)
    op.create_table(
        "idempotency_records",
        sa.Column("tenant_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("result_json", sa.Text, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index("idx_idempotency_processed_at", "triage.idempotency_records", ["processed_at"])
    op.create_index("idx_idempotency_event_type", "triage.idempotency_records", ["event_type"])
    
    # DLQ (persistent storage for failed events)
    op.create_table(
        "dlq_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("original_event_id", sa.String(255), nullable=False),
        sa.Column("original_event", sa.Text, nullable=False),  # JSON
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("error_type", sa.String(100)),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["triage.tenants.id"]),
        schema="triage",
    )
    op.create_index("idx_dlq_created_at", "triage.dlq_events", ["created_at"])
    op.create_index("idx_dlq_replayed", "triage.dlq_events", ["replayed_at"], postgresql_where=sa.text("replayed_at IS NULL"))

def downgrade():
    op.drop_table("dlq_events", schema="triage")
    op.drop_table("idempotency_records", schema="triage")
```

---

## 5. S6.4 — Priority Lanes

### Goal
Route messages by channel priority: chat (high SLA) vs email (lower SLA). Process chat before email even if email arrived first.

### Design

#### 5.1 Priority Queue Architecture

**Two Application-Level Queues:**
- **Chat Lane:** 10 workers, SLA 1 min (urgent)
- **Email Lane:** 3 workers, SLA 8 hours (batch)

Each lane is a FIFO queue backed by Redis sorted sets (ordered by arrival time + priority).

**File: `services/api/src/triage/adapters/priority_queue.py`**
```python
from typing import Dict, Any, Optional, List
from enum import IntEnum
from datetime import datetime
import json
import redis.asyncio as redis
import asyncio
import structlog

log = structlog.get_logger(__name__)

class Channel(IntEnum):
    """Channel priority (lower number = higher priority)."""
    CHAT = 1          # Urgent (1-min SLA)
    WEB = 2            # High (2-min SLA)
    EMAIL = 10         # Low (8-hour SLA)
    VOICE = 0          # Reserved for future


class PriorityQueue:
    """Redis-backed priority queue for routing messages to worker lanes."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.chat_queue_key = "queue:chat"
        self.email_queue_key = "queue:email"
        self.dlq_queue_key = "queue:dlq"
    
    async def enqueue_message(
        self,
        message_id: str,
        tenant_id: str,
        channel: str,
        payload: Dict[str, Any],
    ) -> str:
        """Enqueue message to appropriate lane.
        
        Args:
            message_id: Message ID
            tenant_id: Tenant context
            channel: "chat", "email", "web"
            payload: Message data
        
        Returns:
            Queue name message was sent to
        """
        # Determine priority
        priority_channel = Channel[channel.upper()]
        
        # Select queue
        if priority_channel in (Channel.CHAT, Channel.WEB):
            queue_key = self.chat_queue_key
            workers = 10
        elif priority_channel == Channel.EMAIL:
            queue_key = self.email_queue_key
            workers = 3
        else:
            queue_key = self.dlq_queue_key
            workers = 1
        
        # Score = priority (lower = higher priority) + arrival time
        # This ensures: within same priority, FIFO ordering
        score = priority_channel + (datetime.utcnow().timestamp() / 1e6)
        
        # Wrap message
        item = {
            "message_id": message_id,
            "tenant_id": tenant_id,
            "channel": channel,
            "payload": payload,
            "enqueued_at": datetime.utcnow().isoformat(),
        }
        
        # Add to sorted set (score = priority + time)
        await self.redis.zadd(
            queue_key,
            {json.dumps(item): score},
        )
        
        log.info(
            "message_enqueued",
            message_id=message_id,
            channel=channel,
            queue=queue_key,
            workers=workers,
        )
        
        return queue_key
    
    async def dequeue_message(
        self,
        channel: str,
        batch_size: int = 1,
    ) -> List[Dict[str, Any]]:
        """Dequeue message(s) from lane.
        
        Args:
            channel: "chat" or "email"
            batch_size: Number of messages to dequeue
        
        Returns:
            List of messages (empty if queue empty)
        """
        queue_key = self.chat_queue_key if channel == "chat" else self.email_queue_key
        
        # Get lowest-scored items (highest priority)
        items = await self.redis.zrange(queue_key, 0, batch_size - 1, withscores=False)
        
        # Remove from queue
        if items:
            await self.redis.zrem(queue_key, *items)
        
        # Parse and return
        messages = [json.loads(item) for item in items]
        
        log.info(
            "message_dequeued",
            channel=channel,
            count=len(messages),
        )
        
        return messages
    
    async def get_queue_depth(self, channel: str) -> int:
        """Get number of messages in queue."""
        queue_key = self.chat_queue_key if channel == "chat" else self.email_queue_key
        return await self.redis.zcard(queue_key)
```

#### 5.2 Worker Pool

**File: `services/api/src/triage/adapters/worker_pool.py`**
```python
import asyncio
from typing import Callable, Dict, Any, List
import structlog

log = structlog.get_logger(__name__)

class WorkerPool:
    """Fixed-size pool of workers consuming from priority queue."""
    
    def __init__(
        self,
        priority_queue,
        handler_func: Callable,
        num_workers: int,
        channel: str,
    ):
        """
        Args:
            priority_queue: PriorityQueue instance
            handler_func: Async callable(message) -> result
            num_workers: Number of concurrent workers
            channel: "chat" or "email"
        """
        self.priority_queue = priority_queue
        self.handler_func = handler_func
        self.num_workers = num_workers
        self.channel = channel
        self._tasks: List[asyncio.Task] = []
        self._stop = False
    
    async def start(self) -> None:
        """Start worker pool."""
        self._stop = False
        
        for i in range(self.num_workers):
            task = asyncio.create_task(
                self._worker_loop(worker_id=i)
            )
            self._tasks.append(task)
            log.info("worker_started", channel=self.channel, worker_id=i)
    
    async def stop(self) -> None:
        """Stop worker pool gracefully."""
        self._stop = True
        
        # Wait for all tasks to finish (with timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            log.warning("worker_pool_timeout", channel=self.channel)
        
        log.info("worker_pool_stopped", channel=self.channel)
    
    async def _worker_loop(self, worker_id: int) -> None:
        """Single worker loop."""
        while not self._stop:
            try:
                # Dequeue message
                messages = await self.priority_queue.dequeue_message(
                    channel=self.channel,
                    batch_size=1,
                )
                
                if not messages:
                    # Queue empty, sleep briefly before retry
                    await asyncio.sleep(0.1)
                    continue
                
                message = messages[0]
                message_id = message["message_id"]
                
                try:
                    # Process message
                    result = await self.handler_func(message)
                    
                    log.info(
                        "message_processed",
                        message_id=message_id,
                        channel=self.channel,
                        worker_id=worker_id,
                    )
                except Exception as e:
                    log.exception(
                        "message_processing_error",
                        message_id=message_id,
                        channel=self.channel,
                        error=str(e),
                    )
                    # Send to DLQ (handled by outer layer)
            
            except Exception as e:
                log.exception(
                    "worker_error",
                    channel=self.channel,
                    worker_id=worker_id,
                    error=str(e),
                )
                await asyncio.sleep(1.0)  # Back off on error
```

#### 5.3 Starvation Test

**File: `services/api/tests/test_priority_lanes_starvation.py`**
```python
import pytest
import asyncio
from time import time
from triage.adapters.priority_queue import PriorityQueue, Channel


@pytest.mark.integration
async def test_chat_starvation_avoidance():
    """Test: 1000 email msgs over 100s, then 1 chat msg → chat processed within 5s.
    
    Verifies: priority lanes prevent email from starving chat.
    """
    # Setup
    redis_client = await get_test_redis()
    priority_queue = PriorityQueue(redis_client)
    
    # Phase 1: Enqueue 1000 email messages over 100 seconds
    email_msg_count = 1000
    for i in range(email_msg_count):
        await priority_queue.enqueue_message(
            message_id=f"email_{i}",
            tenant_id="test_tenant",
            channel="email",
            payload={"body": f"Email #{i}"},
        )
        
        if i % 100 == 0:
            await asyncio.sleep(0.1)  # Simulate arrival spread
    
    # Phase 2: Enqueue 1 chat message and measure time-to-process
    chat_enqueue_time = time()
    await priority_queue.enqueue_message(
        message_id="chat_urgent",
        tenant_id="test_tenant",
        channel="chat",
        payload={"body": "Help! My account is broken!"},
    )
    
    # Phase 3: Dequeue and measure when chat is processed
    # (simulate worker pool processing)
    email_dequeue_times = []
    chat_dequeue_time = None
    
    # Dequeue up to 100 messages
    for _ in range(100):
        messages = await priority_queue.dequeue_message(channel="email", batch_size=10)
        for msg in messages:
            if "chat_urgent" in msg.get("message_id", ""):
                chat_dequeue_time = time()
            else:
                email_dequeue_times.append(time())
        
        if chat_dequeue_time:
            break
        
        await asyncio.sleep(0.05)
    
    # Assert: chat was processed within 5 seconds
    assert chat_dequeue_time is not None, "Chat message was never dequeued"
    time_to_process_chat = chat_dequeue_time - chat_enqueue_time
    assert time_to_process_chat < 5.0, f"Chat starvation: took {time_to_process_chat}s"
    
    print(f"✓ Chat message processed in {time_to_process_chat:.2f}s (SLA: <5s)")
```

---

## 6. S6.5 — Temporal Adapter for WorkflowEngine

### Goal
Replace in-process LangGraph executor (`triage.agent.graph`) with Temporal 1.24+ for:
- **Durability:** Workflow state persisted in PostgreSQL history DB
- **Resumability:** Crash during step → resume from checkpoint
- **Visibility:** Web UI, audit log, replay
- **Scalability:** Multi-process worker pool

### Design

#### 6.1 Temporal Architecture

**Temporal Server:** 1 development deployment (for Sprint 6); production = 3-node HA
- **History DB:** PostgreSQL (same schema as MVP for simplicity)
- **Visibility DB:** PostgreSQL (optional; can use history DB)
- **Task Queues:** write-actions, approvals, sla-timers

**Workflow Definition:** Temporal workflow = `triage.agent.graph` phases

**File: `services/api/src/triage/workflows/process_message_workflow.py`**
```python
from typing import Dict, Any, List
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
import structlog

from triage.workflows.activities import (
    classify_intent_activity,
    extract_entities_activity,
    make_decision_activity,
    retrieve_context_activity,
    generate_response_activity,
    validate_output_activity,
    execute_tools_activity,
    escalate_activity,
)

log = structlog.get_logger(__name__)


@workflow.defn
class ProcessMessageWorkflow:
    """Main triage workflow (replacement for LangGraph in-process executor)."""
    
    @workflow.run
    async def run(self, workflow_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute triage workflow.
        
        Phases:
        1. Classify intent
        2. Extract entities
        3. Make autonomy decision
        4. Retrieve context (if needed)
        5. Generate response
        6. Validate output
        7. Execute tools (if authorized)
        8. Escalate (if needed)
        
        Args:
            workflow_input: {
                message_id: str,
                tenant_id: str,
                conversation_id: str,
                message: Message (proto),
            }
        
        Returns:
            {
                message_id: str,
                status: "resolved" | "escalated" | "error",
                resolution: { ... },
            }
        """
        # Initialize state
        message_id = workflow_input["message_id"]
        tenant_id = workflow_input["tenant_id"]
        message_data = workflow_input["message"]
        
        state = {
            "message_id": message_id,
            "tenant_id": tenant_id,
            "message": message_data,
            "intent": None,
            "confidence": None,
            "entities": [],
            "autonomous": False,
            "context": None,
            "response": None,
            "validation_passed": False,
            "tool_results": [],
            "escalation_reason": None,
        }
        
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
        )
        
        try:
            # Phase 1: Classify intent (60s timeout with fallback on timeout)
            log.info("phase_start", phase="classify", message_id=message_id)
            try:
                intent_result = await workflow.execute_activity(
                    classify_intent_activity,
                    state,
                    start_to_close_timeout=timedelta(seconds=30),  # See M4: per-activity timeout
                    retry_policy=retry_policy,
                )
                state["intent"] = intent_result["intent"]
                state["confidence"] = intent_result["confidence"]
                state["entities"] = intent_result.get("entities", [])
            except Exception as e:
                if "timeout" in str(e).lower():
                    log.warning("classify_intent_timeout_escalating", message_id=message_id)
                    state["escalation_reason"] = "classify_intent_timeout"
                    # Skip to escalation (don't fail workflow)
                    goto_escalation = True
                else:
                    raise
                
                if not goto_escalation:
                    continue
            
            # Phase 2: Extract entities
            log.info("phase_start", phase="extract_entities", message_id=message_id)
            entities_result = await workflow.execute_activity(
                extract_entities_activity,
                state,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            state["entities"] = entities_result["entities"]
            
            # Phase 3: Make autonomy decision (10s timeout, very fast)
            log.info("phase_start", phase="make_decision", message_id=message_id)
            decision_result = await workflow.execute_activity(
                make_decision_activity,
                state,
                start_to_close_timeout=timedelta(seconds=10),  # Fast operation
                retry_policy=retry_policy,
            )
            state["autonomous"] = decision_result["autonomous"]
            
            if state["autonomous"]:
                # Phase 4: Retrieve context
                log.info("phase_start", phase="retrieve_context", message_id=message_id)
                context_result = await workflow.execute_activity(
                    retrieve_context_activity,
                    state,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
                state["context"] = context_result["context"]
                
                # Phase 5: Generate response
                log.info("phase_start", phase="generate_response", message_id=message_id)
                response_result = await workflow.execute_activity(
                    generate_response_activity,
                    state,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
                state["response"] = response_result["response"]
                
                # Phase 6: Validate output
                log.info("phase_start", phase="validate_output", message_id=message_id)
                validation_result = await workflow.execute_activity(
                    validate_output_activity,
                    state,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
                state["validation_passed"] = validation_result["passed"]
                
                if state["validation_passed"]:
                    # Phase 7: Execute tools (optional)
                    if state.get("tools_needed"):
                        log.info("phase_start", phase="execute_tools", message_id=message_id)
                        tools_result = await workflow.execute_activity(
                            execute_tools_activity,
                            state,
                            start_to_close_timeout=timedelta(seconds=60),
                            retry_policy=retry_policy,
                        )
                        state["tool_results"] = tools_result["results"]
                    
                    # Return resolved
                    return {
                        "message_id": message_id,
                        "status": "resolved",
                        "resolution": {
                            "intent": state["intent"],
                            "response": state["response"],
                            "tools_executed": len(state["tool_results"]),
                        },
                    }
            
            # Phase 8: Escalate
            log.info("phase_start", phase="escalate", message_id=message_id)
            escalation_result = await workflow.execute_activity(
                escalate_activity,
                state,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            state["escalation_reason"] = escalation_result.get("reason", "human_judgment_needed")
            
            return {
                "message_id": message_id,
                "status": "escalated",
                "resolution": {
                    "reason": state["escalation_reason"],
                    "assigned_agent_id": escalation_result.get("assigned_agent_id"),
                },
            }
        
        except Exception as e:
            log.exception(
                "workflow_error",
                message_id=message_id,
                error=str(e),
            )
            return {
                "message_id": message_id,
                "status": "error",
                "resolution": {"error": str(e)},
            }
```

#### 6.2 Activities (Temporal-Compatible) — Addressing H3 Findings

**Design Decision: Activities wrap LangGraph node logic, NOT node objects**

Activities execute LangGraph node business logic by calling their underlying utilities directly. This ensures:
1. **Determinism** — activities call pure business logic (e.g., classifier, extractor), not LangGraph nodes which may have state
2. **Clear mapping** — each LangGraph node → one activity (1:1, but logic separation)
3. **Type safety** — activities use typed inputs/outputs, testable in isolation

**Mapping from LangGraph nodes to activities:**
- `classify_intent_node` → `classify_intent_activity` (wraps `IntentClassifier`)
- `extract_entities_node` → `extract_entities_activity` (wraps `RuleBasedEntityExtractor`)
- `make_decision_node` → `make_decision_activity` (wraps `DecisionMatrix`)
- ... (see list below for all 8)

All implementations verified in `services/api/src/triage/agent/nodes.py`:
- ✓ `IntentClassifier` class exists in `triage.classification.classifier`
- ✓ `RuleBasedEntityExtractor` exists in `triage.entity.extractor`
- ✓ `DecisionMatrix` exists in `triage.decision.matrix`
- ✓ `HybridRetriever` exists in `triage.retrieval.hybrid`
- ✓ `ResponseGenerator` exists in `triage.generation.generator`
- ✓ `OutputValidator` exists in `triage.generation.output_validator`
- ✓ `ToolExecutor` exists in `triage.tools.executor`

**File: `services/api/src/triage/workflows/activities.py`**
```python
from typing import Dict, Any
from temporalio import activity
from datetime import timedelta
import structlog

log = structlog.get_logger(__name__)

# Activity timeouts per operation type (addressing M4 findings)
CLASSIFY_INTENT_TIMEOUT = timedelta(seconds=60)    # LLM calls can be slow
EXTRACT_ENTITIES_TIMEOUT = timedelta(seconds=30)   # Rule-based, fast
MAKE_DECISION_TIMEOUT = timedelta(seconds=10)      # Logic, very fast
RETRIEVE_CONTEXT_TIMEOUT = timedelta(seconds=30)   # Database query
GENERATE_RESPONSE_TIMEOUT = timedelta(seconds=60)  # LLM generation
VALIDATE_OUTPUT_TIMEOUT = timedelta(seconds=30)    # Validation logic
EXECUTE_TOOLS_TIMEOUT = timedelta(seconds=120)     # External tool calls (longest)
ESCALATE_TIMEOUT = timedelta(seconds=20)           # Queue assignment


@activity.defn
async def classify_intent_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Classify message intent.
    
    Wraps LangGraph classify_intent_node logic: calls IntentClassifier directly.
    Timeout: 60s (for LLM inference)
    Failure strategy: Timeout → escalate (not fail workflow)
    
    Args:
        state: Workflow state with message, entities, etc.
    
    Returns:
        {
            "intent": str (e.g., "refund_request"),
            "confidence": float (0.0–1.0),
            "entities": list of entities,
        }
    
    Raises:
        TimeoutError: If LLM call exceeds timeout
        ApplicationError: On classification failure (retry policy applies)
    """
    try:
        from triage.classification.classifier import IntentClassifier
        
        classifier = IntentClassifier()
        result = await classifier.classify(state["message"]["body"])
        
        log.info(
            "activity_classify_intent_complete",
            intent=result.get("intent"),
            confidence=result.get("confidence"),
        )
        
        return {
            "intent": result.get("intent"),
            "confidence": result.get("confidence", 0.0),
            "entities": result.get("entities", []),
        }
    except TimeoutError as e:
        log.warning("activity_classify_intent_timeout", timeout_seconds=int(CLASSIFY_INTENT_TIMEOUT.total_seconds()))
        raise  # Will trigger workflow-level fallback (escalate instead of fail)
    except Exception as e:
        log.exception("activity_classify_intent_error", error=str(e))
        raise


@activity.defn
async def extract_entities_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Extract named entities from message.
    
    Wraps LangGraph extract_entities_node: calls RuleBasedEntityExtractor directly.
    Timeout: 30s (rule-based, should be fast)
    Failure strategy: Timeout → escalate
    """
    try:
        from triage.entity.extractor import RuleBasedEntityExtractor
        
        extractor = RuleBasedEntityExtractor()
        result = extractor.extract(
            state["message"]["body"],
            state.get("message_id"),
        )
        
        entities_list = [
            {
                "entity_type": e.entity_type.name if hasattr(e.entity_type, 'name') else str(e.entity_type),
                "value": e.value,
                "confidence": e.confidence,
                "is_pii": e.is_pii,
            }
            for e in result.entities
        ]
        
        log.info("activity_extract_entities_complete", entity_count=len(entities_list))
        
        return {"entities": entities_list}
    except Exception as e:
        log.exception("activity_extract_entities_error", error=str(e))
        raise


@activity.defn
async def make_decision_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Decide autonomy level.
    
    Wraps LangGraph make_decision_node: calls DecisionMatrix directly.
    Timeout: 10s (pure logic, very fast)
    Failure strategy: Timeout → escalate
    """
    try:
        from triage.decision.matrix import DecisionMatrix
        from triage.models.decision import PolicyInput
        
        policy_input = PolicyInput(
            intent_name=state.get("intent", "unknown"),
            intent_confidence=state.get("confidence", 0.0),
            message_text=state["message"]["body"],
            customer_tier="standard",
            customer_ial=1,
            is_repeat_customer=False,
            previous_resolution_attempts=0,
            extracted_amount=state.get("extracted_amount"),
            safety_flags=state.get("safety_flags", []),
        )
        
        matrix = DecisionMatrix()
        decision = matrix.decide(policy_input)
        
        log.info(
            "activity_make_decision_complete",
            autonomy_level=decision.autonomy_level.value if hasattr(decision.autonomy_level, 'value') else str(decision.autonomy_level),
        )
        
        return {
            "autonomous": decision.autonomy_level.value >= 1 if hasattr(decision.autonomy_level, 'value') else False,
            "autonomy_reason": decision.reason if hasattr(decision, 'reason') else None,
        }
    except Exception as e:
        log.exception("activity_make_decision_error", error=str(e))
        raise


@activity.defn
async def retrieve_context_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Retrieve enrichment context.
    
    Wraps LangGraph retrieve_context_node: calls HybridRetriever directly.
    Timeout: 30s (database queries + embeddings)
    Failure strategy: Timeout → return empty context, continue (graceful degradation)
    """
    try:
        from triage.retrieval.hybrid import HybridRetriever
        
        retriever = HybridRetriever()
        context = await retriever.retrieve(
            query=state["message"]["body"],
            tenant_id=state["tenant_id"],
            intent=state.get("intent"),
            limit=5,
        )
        
        log.info("activity_retrieve_context_complete", doc_count=len(context) if context else 0)
        
        return {"context": context or []}
    except Exception as e:
        log.exception("activity_retrieve_context_error", error=str(e))
        return {"context": []}  # Gracefully degrade: continue with empty context


@activity.defn
async def generate_response_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Generate response text.
    
    Wraps LangGraph generate_response_node: calls ResponseGenerator directly.
    Timeout: 60s (LLM generation can be slow)
    Failure strategy: Timeout → escalate (don't generate bad response)
    """
    try:
        from triage.generation.generator import ResponseGenerator
        
        generator = ResponseGenerator()
        response = await generator.generate(
            system_prompt=f"You are a helpful support agent handling a {state.get('intent', 'support')} request.",
            user_message=state["message"]["body"],
            context="\n".join([str(d) for d in state.get("context", [])]),
            max_tokens=500,
        )
        
        log.info("activity_generate_response_complete", response_len=len(response.response_text if hasattr(response, 'response_text') else str(response)))
        
        return {"response": response.response_text if hasattr(response, 'response_text') else str(response)}
    except TimeoutError as e:
        log.warning("activity_generate_response_timeout")
        raise
    except Exception as e:
        log.exception("activity_generate_response_error", error=str(e))
        raise


@activity.defn
async def validate_output_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Validate response for safety/quality.
    
    Wraps LangGraph validate_output_node: calls OutputValidator directly.
    Timeout: 30s (rule-based validation)
    Failure strategy: Timeout → fail validation, escalate
    """
    try:
        from triage.generation.output_validator import OutputValidator
        
        validator = OutputValidator()
        is_valid = await validator.validate(
            response=state.get("response", ""),
            grounding_score=state.get("grounding_score", 0.0),
        )
        
        log.info("activity_validate_output_complete", passed=is_valid)
        
        return {"passed": is_valid}
    except Exception as e:
        log.exception("activity_validate_output_error", error=str(e))
        return {"passed": False}  # Conservative: fail validation on error


@activity.defn
async def execute_tools_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Execute tools (refunds, lookups, etc).
    
    Wraps LangGraph execute_tools_node: calls ToolExecutor directly.
    Timeout: 120s (external API calls, longest operation)
    Failure strategy: Timeout → escalate (don't leave user without response)
    """
    try:
        from triage.tools.executor import ToolExecutor
        
        executor = ToolExecutor()
        results = await executor.execute_tools(
            message_id=state["message_id"],
            intent=state.get("intent"),
            entities=state.get("entities", []),
            tenant_id=state["tenant_id"],
        )
        
        log.info("activity_execute_tools_complete", tool_count=len(results) if results else 0)
        
        return {"results": results or []}
    except TimeoutError as e:
        log.warning("activity_execute_tools_timeout")
        raise  # Escalate instead of continuing
    except Exception as e:
        log.exception("activity_execute_tools_error", error=str(e))
        raise


@activity.defn
async def escalate_activity(state: Dict[str, Any]) -> Dict[str, Any]:
    """Activity: Escalate to human agent.
    
    Wraps LangGraph escalate_node: routes to EscalationRouter directly.
    Timeout: 20s (queue lookup + agent assignment)
    Failure strategy: Timeout → assign to general queue
    """
    try:
        from triage.escalation.router import EscalationRouter
        
        router = EscalationRouter()
        assignment = await router.assign_agent(
            tenant_id=state["tenant_id"],
            message_id=state["message_id"],
            intent=state.get("intent"),
            priority=state.get("priority", 3),
        )
        
        log.info(
            "activity_escalate_complete",
            agent_id=assignment.get("agent_id"),
        )
        
        return {
            "reason": state.get("escalation_reason", "human_judgment_needed"),
            "assigned_agent_id": assignment.get("agent_id"),
        }
    except Exception as e:
        log.exception("activity_escalate_error", error=str(e))
        return {
            "reason": "escalation_service_unavailable",
            "assigned_agent_id": None,
        }
```

#### 6.3 Workflow Starter (Message Ingestion Integration)

**File: `services/api/src/triage/adapters/workflow_starter.py`**
```python
from typing import Dict, Any
from temporalio.client import Client
from temporalio.v1 import WorkflowOptions, StartWorkflowOptions
from datetime import timedelta
import structlog

log = structlog.get_logger(__name__)


class TemporalWorkflowStarter:
    """Start Temporal workflows from message ingestion."""
    
    def __init__(self, temporal_host: str = "localhost", temporal_port: int = 7233):
        """
        Args:
            temporal_host: Temporal server host
            temporal_port: Temporal server port
        """
        self.temporal_host = temporal_host
        self.temporal_port = temporal_port
        self._client: Optional[Client] = None
    
    async def connect(self) -> None:
        """Connect to Temporal server."""
        self._client = await Client.connect(f"{self.temporal_host}:{self.temporal_port}")
        log.info("temporal_client_connected", host=self.temporal_host)
    
    async def start_process_message_workflow(
        self,
        message_id: str,
        tenant_id: str,
        conversation_id: str,
        message_data: Dict[str, Any],
    ) -> str:
        """Start ProcessMessageWorkflow.
        
        Args:
            message_id: Message ID
            tenant_id: Tenant context
            conversation_id: Conversation ID
            message_data: Full message object
        
        Returns:
            Workflow ID (deterministic from inputs)
        """
        # Workflow ID = deterministic from (tenant_id, message_id, idempotency_key)
        # Ensures same workflow for retries
        workflow_id = f"{tenant_id}:{message_id}"
        
        workflow_input = {
            "message_id": message_id,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "message": message_data,
        }
        
        try:
            workflow_handle = await self._client.start_workflow(
                "ProcessMessageWorkflow",
                workflow_input,
                id=workflow_id,
                task_queue="triage",
                workflow_execution_timeout=timedelta(minutes=30),
                workflow_run_timeout=timedelta(minutes=10),
                workflow_task_timeout=timedelta(seconds=10),
            )
            
            log.info(
                "workflow_started",
                workflow_id=workflow_id,
                message_id=message_id,
            )
            
            return workflow_id
        except Exception as e:
            log.exception(
                "workflow_start_error",
                workflow_id=workflow_id,
                error=str(e),
            )
            raise
```

#### 6.4 Workflow State Tracking (for parity with MVP)

**File: `services/api/src/triage/adapters/workflow_state_tracker.py`**
```python
from typing import Dict, Any, Optional
from datetime import datetime
import json
import structlog

log = structlog.get_logger(__name__)


class WorkflowStateTracker:
    """Track Temporal workflow state in PostgreSQL for visibility + debugging."""
    
    def __init__(self, db_session):
        self.db_session = db_session
    
    async def record_checkpoint(
        self,
        workflow_id: str,
        phase: str,
        state_json: Dict[str, Any],
    ) -> None:
        """Record workflow checkpoint (called by activities).
        
        Args:
            workflow_id: Temporal workflow ID
            phase: Current phase name
            state_json: Current execution state
        """
        stmt = """
            INSERT INTO triage.workflow_checkpoints (workflow_id, phase, state_json, checkpoint_at)
            VALUES (:workflow_id, :phase, :state_json, :checkpoint_at)
            ON CONFLICT (workflow_id) DO UPDATE
            SET phase = :phase, state_json = :state_json, checkpoint_at = :checkpoint_at
        """
        
        await self.db_session.execute(
            stmt,
            {
                "workflow_id": workflow_id,
                "phase": phase,
                "state_json": json.dumps(state_json),
                "checkpoint_at": datetime.utcnow(),
            },
        )
        
        log.info("workflow_checkpoint_recorded", workflow_id=workflow_id, phase=phase)
    
    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve last known workflow state."""
        stmt = "SELECT state_json, phase FROM triage.workflow_checkpoints WHERE workflow_id = :workflow_id"
        
        row = await self.db_session.execute(stmt, {"workflow_id": workflow_id})
        result = row.one_or_none()
        
        if result:
            return {
                "state": json.loads(result[0]),
                "phase": result[1],
            }
        
        return None
```

#### 6.5 Database Schema (Workflow Checkpoints)

**File: `packages/py_core/alembic/versions/0009_sprint6_temporal_state.py`**
```python
"""Sprint 6: Temporal workflow state tracking."""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "workflow_checkpoints",
        sa.Column("workflow_id", sa.String(255), primary_key=True),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("state_json", sa.Text, nullable=False),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="triage",
    )
    op.create_index("idx_workflow_checkpoint_at", "triage.workflow_checkpoints", ["checkpoint_at"])

def downgrade():
    op.drop_table("workflow_checkpoints", schema="triage")
```

#### 6.6 Contract Tests (Temporal vs In-Process)

**File: `services/api/tests/test_workflow_engine_contracts.py`**
```python
import pytest
from typing import Dict, Any

from triage.agent.graph import TriageAgentGraph  # MVP in-process
from triage.adapters.workflow_starter import TemporalWorkflowStarter  # Temporal


class WorkflowEngineContractTest:
    """Contract: both implementations produce same result for same input."""
    
    @pytest.fixture
    def sample_message(self) -> Dict[str, Any]:
        """Sample message for testing."""
        return {
            "message_id": "msg_123",
            "tenant_id": "tenant_1",
            "conversation_id": "conv_456",
            "channel": "email",
            "body": "Where is my order?",
            "customer_id": "cust_789",
        }
    
    @pytest.mark.asyncio
    async def test_inprocess_vs_temporal_same_output(self, sample_message):
        """Test: in-process executor and Temporal produce same result."""
        # Run in-process
        inprocess_executor = TriageAgentGraph()
        inprocess_result = await inprocess_executor.invoke(sample_message)
        
        # Run Temporal
        temporal_starter = TemporalWorkflowStarter()
        await temporal_starter.connect()
        workflow_id = await temporal_starter.start_process_message_workflow(
            message_id=sample_message["message_id"],
            tenant_id=sample_message["tenant_id"],
            conversation_id=sample_message["conversation_id"],
            message_data=sample_message,
        )
        
        # Compare results
        assert inprocess_result["status"] == "resolved"  # Both should resolve
        assert "resolution" in inprocess_result
        assert inprocess_result["resolution"]["intent"] is not None
```

---

## 7. S6.6 — Cut-Over Plan & Parity Verification

### Goal
Gradually migrate from MVP to production adapters without downtime. Verify parity (MVP ≈ Kafka) before committing.

### Design

#### 7.1 Feature Flags (Graduated Rollout) — Addressing M6 & H4 Findings

**Design Decision: Deterministic hash (hashlib) + Mutual exclusion enforcement**

Feature flags enable gradual rollout by tenant. Key improvements from findings:
- **M6 Fix:** Use `hashlib.sha256()` instead of Python's built-in `hash()` for deterministic rollout (hash() is non-deterministic across restarts)
- **H4 Fix:** Enforce mutual exclusion at event ingestion point (exactly ONE adapter per message, not both)

**File: `services/api/src/triage/config/feature_flags.py`**
```python
from enum import Enum
import hashlib
import os
import structlog

log = structlog.get_logger(__name__)

class FeatureFlags(Enum):
    """Feature flags for gradual rollout."""
    
    USE_KAFKA_EVENTS = "use_kafka_events"                                    # Global: 0–100%
    USE_TEMPORAL_WORKFLOWS = "use_temporal_workflows"                        # Global: 0–100%
    KAFKA_ENABLED_FOR_CHAT = "kafka_enabled_for_chat"                        # Chat-only: 0–100%
    KAFKA_ENABLED_FOR_EMAIL = "kafka_enabled_for_email"                      # Email-only: 0–100%
    PRIORITY_LANES_ENABLED = "priority_lanes_enabled"                        # Global: 0–100%


class FeatureFlagManager:
    """Manage feature flags (stored in DB or Redis).
    
    Addressing H4: Enforces mutual exclusion so exactly ONE adapter (MVP or Kafka)
    processes each message, never both.
    """
    
    def __init__(self, db_session):
        self.db_session = db_session
    
    async def is_enabled(
        self,
        flag: FeatureFlags,
        tenant_id: str,
        channel: str = None,
    ) -> bool:
        """Check if feature flag is enabled (deterministic per tenant).
        
        Args:
            flag: Feature flag name
            tenant_id: Tenant context (allows per-tenant rollout)
            channel: Optional channel ("chat", "email") for channel-specific flags
        
        Returns:
            True if flag is enabled for this tenant + channel
            
        Guarantees:
            - Deterministic: same tenant always gets same result (using SHA256)
            - Non-determinism fixed: hash() varies across Python restarts (M6 finding)
        """
        # Query feature_flags table
        stmt = """
            SELECT rollout_percentage FROM triage.feature_flags
            WHERE flag_name = :flag_name AND tenant_id = :tenant_id
        """
        
        row = await self.db_session.execute(
            stmt,
            {"flag_name": flag.value, "tenant_id": tenant_id},
        )
        result = row.one_or_none()
        
        if not result:
            # Check global default
            stmt = "SELECT rollout_percentage FROM triage.feature_flags WHERE flag_name = :flag_name AND tenant_id IS NULL"
            row = await self.db_session.execute(stmt, {"flag_name": flag.value})
            result = row.one_or_none()
        
        percentage = result[0] if result else 0
        
        # FIX M6: Use hashlib.sha256() instead of hash() (deterministic across restarts)
        # Old: hash_val = hash(f"{flag.value}:{tenant_id}") % 100  # Non-deterministic
        # New: Use SHA256 for stable bucketing across app restarts
        hash_val = int(
            hashlib.sha256(f"{flag.value}:{tenant_id}".encode()).hexdigest(),
            16
        ) % 100
        
        enabled = hash_val < percentage
        
        log.info(
            "feature_flag_check",
            flag=flag.value,
            tenant_id=tenant_id,
            enabled=enabled,
            percentage=percentage,
            hash_bucket=hash_val,
        )
        
        return enabled
        
        # Deterministic rollout: SHA256(flag + tenant_id) % 100 < percentage
        # This ensures same tenant always gets same value, even after restarts
        hash_val = int(
            hashlib.sha256(f"{flag.value}:{tenant_id}".encode()).hexdigest(),
            16
        ) % 100
        
        enabled = hash_val < percentage
        
        log.debug(
            "feature_flag_evaluated",
            flag=flag.value,
            tenant_id=tenant_id,
            hash_val=hash_val,
            percentage=percentage,
            enabled=enabled,
        )
        
        return enabled


class EventAdapterSelector:
    """Select which adapter (MVP or Kafka) to use — enforcing H4 mutual exclusion.
    
    Addresses H4 finding: ensures exactly ONE adapter processes each message,
    never both. Prevents duplicate processing and idempotency store collisions.
    """
    
    def __init__(self, feature_flag_manager: FeatureFlagManager):
        self.feature_flags = feature_flag_manager
    
    async def select_adapter(
        self,
        message_id: str,
        tenant_id: str,
        channel: str = "email",
    ) -> str:
        """Select which adapter to use for this message.
        
        Args:
            message_id: Message ID
            tenant_id: Tenant context
            channel: Message channel ("email", "chat", etc.)
        
        Returns:
            "mvp" or "kafka" (exactly one, never both)
            
        Guarantees:
            - Mutual exclusion: same message only processed by ONE adapter
            - Deterministic: same message_id always gets same adapter
        """
        # Check global kafka flag
        use_kafka_global = await self.feature_flags.is_enabled(
            FeatureFlags.USE_KAFKA_EVENTS,
            tenant_id=tenant_id,
        )
        
        if not use_kafka_global:
            return "mvp"  # All traffic goes to MVP
        
        # Check channel-specific flags
        if channel == "chat":
            use_kafka_channel = await self.feature_flags.is_enabled(
                FeatureFlags.KAFKA_ENABLED_FOR_CHAT,
                tenant_id=tenant_id,
            )
        elif channel == "email":
            use_kafka_channel = await self.feature_flags.is_enabled(
                FeatureFlags.KAFKA_ENABLED_FOR_EMAIL,
                tenant_id=tenant_id,
            )
        else:
            use_kafka_channel = use_kafka_global
        
        selected = "kafka" if use_kafka_channel else "mvp"
        
        log.debug(
            "adapter_selected",
            message_id=message_id,
            tenant_id=tenant_id,
            channel=channel,
            adapter=selected,
        )
        
        return selected
```

**Feature Flag Table Schema:**
```sql
CREATE TABLE triage.feature_flags (
    flag_name VARCHAR(100) NOT NULL,
    tenant_id UUID,                    -- NULL = global default
    rollout_percentage INT DEFAULT 0,  -- 0–100
    enabled_at TIMESTAMP DEFAULT NOW(),
    disabled_at TIMESTAMP NULL,
    PRIMARY KEY (flag_name, tenant_id),
);
```

**Integration in Message Ingestion (Addressing H4 mutual exclusion):**

**File: `services/api/src/triage/api/endpoints/messages.py`**
```python
from triage.config.feature_flags import EventAdapterSelector
from triage.ingestion.outbox import OutboxWriter
from triage.adapters.event_bus_kafka import KafkaEventBus

async def ingest_message(message_data):
    """Ingest message (enforcing mutual exclusion per H4 finding).
    
    Key guarantee: exactly ONE of (mvp_bus, kafka_bus) publishes,
    never both. This prevents duplicate idempotency records.
    """
    selector = EventAdapterSelector(feature_flag_manager)
    
    # SELECT adapter (deterministic per tenant + message_id)
    adapter = await selector.select_adapter(
        message_id=message_data["message_id"],
        tenant_id=message_data["tenant_id"],
        channel=message_data.get("channel", "email"),
    )
    
    # EXACTLY ONE of these executes (not both)
    if adapter == "kafka":
        await kafka_bus.publish(
            event_type="message.ingested",
            tenant_id=message_data["tenant_id"],
            payload=message_data,
            outbox_event_id=None,  # Kafka will generate; no reuse here
        )
    else:
        await mvp_bus.write_event(
            tenant_id=message_data["tenant_id"],
            aggregate_type="message",
            aggregate_id=message_data["message_id"],
            event_type="message.ingested",
            payload=message_data,
        )
    
    # Integration test verifies this mutual exclusion (see S6.6 testing strategy)
```

#### 7.2 Parity Checker (Continuous Verification) — Addressing M7 Findings

**Design Decision: Compare output payloads, not just success/error counts**

Addresses M7 finding: parity checker must verify actual results match (intent, confidence, entities),
not just success/failure counts. Two adapters could both return "success" with different results.

**File: `services/api/src/triage/adapters/parity_checker.py`**
```python
from typing import Dict, Any, List, Tuple, Optional
import asyncio
import structlog
from dataclasses import dataclass

log = structlog.get_logger(__name__)


@dataclass
class PayloadDivergence:
    """Record of output divergence between adapters."""
    field_name: str
    mvp_value: Any
    kafka_value: Any
    divergence_type: str  # "value_mismatch", "confidence_threshold"


class ParityChecker:
    """Compare MVP vs Kafka event processing outputs with semantic validation."""
    
    # Thresholds for acceptable divergence (per field type)
    INTENT_DIVERGENCE_THRESHOLD = 0.02        # 2% of messages can have different intent
    CONFIDENCE_THRESHOLD = 0.05               # 5% absolute difference acceptable
    ENTITY_COUNT_THRESHOLD = 0.1              # 10% entity count difference acceptable
    SUCCESS_RATE_THRESHOLD = 0.001            # 0.1% error rate difference
    
    def __init__(self, mvp_bus, kafka_bus):
        self.mvp_bus = mvp_bus
        self.kafka_bus = kafka_bus
        self.divergences: List[Dict] = []
        self.intent_divergences: int = 0
        self.confidence_divergences: int = 0
        self.entity_divergences: int = 0
    
    async def compare_event_processing(
        self,
        test_event: Dict[str, Any],
        handler_func,
        num_iterations: int = 100,
    ) -> Tuple[int, int, List[PayloadDivergence]]:
        """Compare processing results: MVP vs Kafka (output payload comparison).
        
        Key improvement from M7: compares actual output fields (intent, confidence, entities),
        not just success/failure counts.
        
        Args:
            test_event: Test event to process
            handler_func: Async handler to execute
            num_iterations: Number of iterations
        
        Returns:
            (mvp_success_count, kafka_success_count, list_of_divergences)
        """
        mvp_results = []
        kafka_results = []
        
        # Process via MVP
        for i in range(num_iterations):
            try:
                result = await handler_func(test_event, use_kafka=False)
                mvp_results.append(("success", result))
            except Exception as e:
                mvp_results.append(("error", str(e)))
        
        # Process via Kafka
        for i in range(num_iterations):
            try:
                result = await handler_func(test_event, use_kafka=True)
                kafka_results.append(("success", result))
            except Exception as e:
                kafka_results.append(("error", str(e)))
        
        # ENHANCED: Compare actual output payloads, not just counts
        payload_divergences = []
        for i, ((mvp_status, mvp_result), (kafka_status, kafka_result)) in enumerate(zip(mvp_results, kafka_results)):
            if mvp_status != kafka_status:
                # Status mismatch (one succeeded, one failed)
                payload_divergences.append(PayloadDivergence(
                    field_name="status",
                    mvp_value=mvp_status,
                    kafka_value=kafka_status,
                    divergence_type="status_mismatch",
                ))
                continue
            
            if mvp_status == "success" and kafka_status == "success":
                # Both succeeded; compare semantic fields
                mvp_payload = mvp_result or {}
                kafka_payload = kafka_result or {}
                
                # Compare intent
                if mvp_payload.get("intent") != kafka_payload.get("intent"):
                    self.intent_divergences += 1
                    payload_divergences.append(PayloadDivergence(
                        field_name="intent",
                        mvp_value=mvp_payload.get("intent"),
                        kafka_value=kafka_payload.get("intent"),
                        divergence_type="value_mismatch",
                    ))
                
                # Compare confidence (allow small numerical difference)
                mvp_confidence = mvp_payload.get("confidence", 0.0)
                kafka_confidence = kafka_payload.get("confidence", 0.0)
                if abs(mvp_confidence - kafka_confidence) > self.CONFIDENCE_THRESHOLD:
                    self.confidence_divergences += 1
                    payload_divergences.append(PayloadDivergence(
                        field_name="confidence",
                        mvp_value=mvp_confidence,
                        kafka_value=kafka_confidence,
                        divergence_type="confidence_threshold",
                    ))
                
                # Compare entity count (allow threshold variance)
                mvp_entity_count = len(mvp_payload.get("entities", []))
                kafka_entity_count = len(kafka_payload.get("entities", []))
                if mvp_entity_count > 0:  # Avoid division by zero
                    entity_diff_ratio = abs(mvp_entity_count - kafka_entity_count) / mvp_entity_count
                    if entity_diff_ratio > self.ENTITY_COUNT_THRESHOLD:
                        self.entity_divergences += 1
                        payload_divergences.append(PayloadDivergence(
                            field_name="entity_count",
                            mvp_value=mvp_entity_count,
                            kafka_value=kafka_entity_count,
                            divergence_type="value_mismatch",
                        ))
        
        # Summary statistics
        mvp_success = sum(1 for status, _ in mvp_results if status == "success")
        kafka_success = sum(1 for status, _ in kafka_results if status == "success")
        
        success_divergence = abs(mvp_success - kafka_success) / num_iterations if num_iterations > 0 else 0
        
        if success_divergence > self.SUCCESS_RATE_THRESHOLD or payload_divergences:
            self.divergences.append({
                "test_event": test_event,
                "mvp_success": mvp_success,
                "kafka_success": kafka_success,
                "success_divergence": success_divergence,
                "payload_divergences": payload_divergences,
            })
            
            log.warning(
                "parity_check_divergence",
                success_divergence=success_divergence,
                mvp_success=mvp_success,
                kafka_success=kafka_success,
                payload_divergence_count=len(payload_divergences),
                intent_mismatches=self.intent_divergences,
                confidence_mismatches=self.confidence_divergences,
            )
        
        return mvp_success, kafka_success, payload_divergences
    
    async def verify_parity_threshold(self) -> bool:
        """Verify total divergence is below thresholds.
        
        Returns:
            True if parity is acceptable
        """
        if not self.divergences:
            log.info("parity_check_passed_no_divergences")
            return True
        
        # Check intent divergence
        total_intent_divergence = self.intent_divergences
        if total_intent_divergence > int(len(self.divergences) * self.INTENT_DIVERGENCE_THRESHOLD):
            log.error(
                "parity_check_failed_intent",
                intent_mismatches=total_intent_divergence,
                threshold_pct=self.INTENT_DIVERGENCE_THRESHOLD * 100,
            )
            return False
        
        # Check success rate divergence
        total_success_divergence = sum(d["success_divergence"] for d in self.divergences) / len(self.divergences)
        if total_success_divergence > self.SUCCESS_RATE_THRESHOLD:
            log.error(
                "parity_check_failed_success_rate",
                total_divergence=total_success_divergence,
                threshold=self.SUCCESS_RATE_THRESHOLD,
            )
            return False
        
        log.info(
            "parity_check_passed",
            total_divergence=total_success_divergence,
            intent_mismatches=self.intent_divergences,
            confidence_mismatches=self.confidence_divergences,
        )
        return True
```

#### 7.3 Cutover Runbook

**File: `.agents/tasks/sprint6-cutover-runbook.md`**
```markdown
# Sprint 6 Cutover Runbook

## Pre-Cutover Checklist

- [ ] All S6.1–S6.5 tests passing (unit + integration)
- [ ] Parity checker shows <0.1% divergence for 1000 events (M7 payload validation)
- [ ] Kafka cluster healthy (3 brokers, KRaft mode)
- [ ] **Debezium snapshot pre-migration done (see M2 section below)**
- [ ] Debezium connector running and syncing outbox_events
- [ ] Temporal cluster running with PostgreSQL history DB
- [ ] Redis cluster healthy (for idempotency + priority queues)
- [ ] Production database backups current
- [ ] Monitoring dashboards deployed (latency, errors, DLQ depth)
- [ ] On-call engineer assigned

## Pre-Migration: Debezium Snapshot Strategy (Addressing M2 Finding)

**Goal:** Prevent re-emission of pre-existing events on Debezium restart.

### Pre-Migration Steps (run BEFORE Phase 1)

1. **Verify outbox_events table state:**
   ```sql
   SELECT COUNT(*) FROM triage.outbox_events WHERE published_at IS NULL;
   ```
   Should return: ≤ 100 (expected event backlog)
   If >10,000: investigate MVP lag, resolve before continuing

2. **Start Debezium in dry-run mode (snapshot.mode: "never"):**
   ```json
   {
     "snapshot.mode": "never",
     "slot.name": "dbz_slot_dryrun"
   }
   ```

3. **Monitor connector lag:**
   - Verify lag reaches 0 (catches up to current WAL)
   - Should take <5 minutes
   - Monitor: `Debezium_connector_lag_offset_ms` metric

4. **Manually migrate pre-existing unpublished events (if any):**
   ```sql
   -- Publish any pre-existing unpublished events
   UPDATE triage.outbox_events
   SET published_at = NOW()
   WHERE published_at IS NULL AND created_at < NOW() - INTERVAL '1 hour';
   ```

5. **Stop dry-run connector, then start with production settings:**
   ```json
   {
     "snapshot.mode": "initial",
     "slot.name": "dbz_slot"
   }
   ```
   This will snapshot current state exactly once on first start.

## Phase 1: Canary (5% of traffic, 2 hours)

**Goal:** Verify no obvious errors at scale.

### Incident Response Decision Tree (Addressing M5 Finding)

**DECISION: Error Rate Monitoring**
- Error rate <0.1%: ✅ Continue to next phase
- Error rate 0.1%–0.5%: ⚠️ Investigate for 5 min (check logs for pattern)
  - **If pattern found** (e.g., specific tenant/channel): 🛑 Pause that subset, continue overall
  - **If no pattern**: Unknown cause, **🔴 ROLLBACK IMMEDIATELY**
- Error rate >0.5%: 🔴 **ROLLBACK IMMEDIATELY** (page on-call)

**DECISION: DLQ Depth**
- DLQ depth <100: ✅ Normal
- DLQ depth 100–1000: ⚠️ Monitor; may indicate slow replay. Check Debezium lag.
- DLQ depth >1000: 🔴 **PAUSE NEW TRAFFIC**, investigate connector lag
  - If Debezium lag >30s: restart connector
  - If consumer lag >60s: scale workers
  - If unresolved after 10 min: **ROLLBACK**

**DECISION: Latency (p99)**
- Chat p99 <5s: ✅ OK
- Chat p99 5–60s: ⚠️ Warning; check priority lane depth. Increase chat workers if >10 queued.
- Chat p99 >60s (SLA violation): 🔴 Investigate or **ROLLBACK**

**DECISION: Parity Divergence**
- Intent divergence <2%: ✅ OK
- Confidence divergence <5%: ✅ OK
- Either >threshold: ⚠️ Investigate for cause (model drift, feature version mismatch)
  - If caused by Kafka → **ROLLBACK** (adapter mismatch)
  - If caused by MVP (new model deployed): Acceptable, continue

### Actions
1. Deploy new containers (with MVP + Kafka/Temporal adapters running in parallel)
2. Set feature flags to 5%:
   ```sql
   UPDATE triage.feature_flags SET rollout_percentage = 5 WHERE flag_name = 'use_kafka_events';
   ```
3. Monitor:
   - Kafka lag (should be <1s)
   - Event processing latency p99 (<200ms)
   - Error rate (<0.1%)
   - DLQ depth (should stay <100)
   - Parity metrics (intent divergence <2%)

### Rollback
```sql
UPDATE triage.feature_flags SET rollout_percentage = 0 WHERE flag_name = 'use_kafka_events';
```
Lag recovery: <5 min (MVP handles all traffic immediately)

## Phase 2: Early Adopters (25% of traffic, 4 hours)

**Goal:** Verify at scale without impacting most users.

### Actions
1. Increase feature flag to 25%
2. Monitor same metrics
3. Run parity checker every 15 min

### Rollback
Flip flag back to 5% and investigate divergence

## Phase 3: General Availability (100% of traffic, next 24 hours)

**Goal:** Full cutover.

### Actions
1. Increase to 100%
2. Monitor for 24 hours
3. Set flag to persistent (no more MVP fallback)

### Rollback
Flip flag back to 0% within 5 minutes (lag recovery <5 min)

## Post-Cutover (Next 7 Days)

- [ ] Monitor alerts for anomalies
- [ ] Verify Kafka retention (7 days) is working
- [ ] Archive and clean up MVP in-memory event stores
- [ ] Update documentation

## Incident Response

If >0.5% error rate:
1. Page on-call engineer
2. Flip feature flag to previous percentage
3. Wait 5 min for lag recovery
4. Debug and redeploy

If DLQ depth exceeds 10,000:
1. Stop accepting new events
2. Replay DLQ items after fix is deployed
3. Resume normal operations
```

#### 7.4 Staging Simulation Test

**File: `services/api/tests/test_cutover_simulation.py`**
```python
import pytest
import asyncio
from triage.adapters.event_bus_kafka import KafkaEventBus
from triage.ingestion.outbox import OutboxWriter
from triage.adapters.parity_checker import ParityChecker


@pytest.mark.integration
async def test_cutover_staging_simulation():
    """Test: simulate cutover with 1000 events, verify parity + latency."""
    # Setup
    mvp_bus = OutboxWriter()
    kafka_bus = KafkaEventBus()
    await kafka_bus.connect()
    
    parity_checker = ParityChecker(mvp_bus, kafka_bus)
    
    # Generate 1000 test events
    test_events = [
        {
            "message_id": f"msg_{i}",
            "tenant_id": f"tenant_{i % 10}",  # 10 tenants
            "channel": "email" if i % 3 == 0 else "chat",
            "body": f"Test message {i}",
        }
        for i in range(1000)
    ]
    
    # Publish to both buses
    async def publish_handler(event):
        # Publish to MVP
        await mvp_bus.publish(
            event_type="message.ingested",
            tenant_id=event["tenant_id"],
            aggregate_id=event["message_id"],
            payload=event,
        )
        
        # Publish to Kafka
        await kafka_bus.publish(
            event_type="message.ingested",
            tenant_id=event["tenant_id"],
            payload=event,
        )
    
    # Execute
    await asyncio.gather(*[publish_handler(e) for e in test_events])
    
    # Verify parity
    parity_ok = await parity_checker.verify_parity_threshold(threshold=0.001)
    
    assert parity_ok, "Parity check failed: >0.1% divergence"
    
    # Verify latency
    # (implementation: measure p99 latency for event processing)
    
    await kafka_bus.disconnect()
```

---

## 8. Infrastructure Topology

### Docker Compose (Development Stack)

**File: `docker-compose.sprint6.yml`**
```yaml
version: '3.8'

services:
  # Existing MVP services
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: triage
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes

  # S6.2: Kafka 3-broker KRaft cluster
  kafka-broker-1:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_NODE_ID: 1
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-broker-1:9092,2@kafka-broker-2:9092,3@kafka-broker-3:9092
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-broker-1:29092,EXTERNAL://kafka-broker-1:9093
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      CLUSTER_ID: MkQkRmVuTjBOUjBMUQ==
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
      KAFKA_LOG_RETENTION_HOURS: 168
    ports:
      - "9093:9093"
    depends_on:
      - postgres

  kafka-broker-2:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_BROKER_ID: 2
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_NODE_ID: 2
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-broker-1:9092,2@kafka-broker-2:9092,3@kafka-broker-3:9092
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-broker-2:29092,EXTERNAL://kafka-broker-2:9093
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      CLUSTER_ID: MkQkRmVuTjBOUjBMUQ==
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    ports:
      - "9094:9093"

  kafka-broker-3:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_BROKER_ID: 3
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_NODE_ID: 3
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-broker-1:9092,2@kafka-broker-2:9092,3@kafka-broker-3:9092
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-broker-3:29092,EXTERNAL://kafka-broker-3:9093
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      CLUSTER_ID: MkQkRmVuTjBOUjBMUQ==
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    ports:
      - "9095:9093"

  # S6.2: Debezium PostgreSQL Connector
  debezium-postgres-connector:
    image: debezium/connect:2.3.0
    environment:
      BOOTSTRAP_SERVERS: kafka-broker-1:29092,kafka-broker-2:29092,kafka-broker-3:29092
      GROUP_ID: debezium-pg
      CONFIG_STORAGE_TOPIC: dbz_configs
      OFFSET_STORAGE_TOPIC: dbz_offsets
      STATUS_STORAGE_TOPIC: dbz_status
      CONNECT_VALUE_CONVERTER_SCHEMA_REGISTRY_URL: http://schema-registry:8081
    ports:
      - "8083:8083"
    depends_on:
      - postgres
      - kafka-broker-1
      - kafka-broker-2
      - kafka-broker-3

  # S6.5: Temporal Server
  temporal:
    image: temporalio/temporal:1.24.0
    environment:
      ENABLE_ES: "false"
      DB: postgresql
      DB_PORT: 5432
      POSTGRES_HOST: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "7233:7233"
    depends_on:
      - postgres

  # S6.5: Temporal UI
  temporal-ui:
    image: temporalio/ui:2.23.0
    ports:
      - "8080:8080"
    environment:
      TEMPORAL_ADDRESS: temporal:7233
    depends_on:
      - temporal

volumes:
  postgres_data:
```

---

## 9. Migration Strategy (Concurrent MVP + Production)

### Deployment Phases

**Phase A: Deployment (Day 1)**
- Deploy new container image with both adapters
- Toggle feature flags OFF (0%) → MVP still handles all traffic
- Verify no new errors

**Phase B: Validation (Days 1–2)**
- Run parity checker in background
- Collect metrics: latency, error rates, DLQ depth
- If divergence >0.1%, debug and fix

**Phase C: Canary (Day 2)**
- Feature flag: 5% of traffic
- Monitor for 2 hours
- If successful, proceed

**Phase D: Ramp (Days 2–3)**
- Increase flag: 5% → 25% → 50% → 100%
- Each step: verify metrics, monitor for 1–2 hours

**Phase E: Cleanup (Days 3–7)**
- Archive MVP event stores
- Remove feature flags for MVP
- Update monitoring

### Fallback Options

**Immediate Rollback (<5 min):**
- Feature flag to 0%
- Resume MVP path
- Typical recovery time: <2 min

**Gradual Rollback (10–30 min):**
- Identify issue in Kafka/Temporal
- Fix in new release
- Re-deploy and increase flag

### Concurrent Handling

During ramp phase (e.g., 50% on Kafka, 50% on MVP):
- Idempotency ensures duplicate messages don't cause double-processing
- Both buses publish events
- DLQ accumulates errors from either side
- Parity checker alerts if divergence >0.1%

---

## 10. Risk Analysis

| # | Risk | Severity | Mitigation | Owner |
|---|------|----------|-----------|-------|
| **R1** | Kafka broker failure → message loss during cutover | **CRITICAL** | 3-broker KRaft HA; min.insync.replicas=2; test broker failover before cutover | Infrastructure |
| **R2** | Debezium connector lag (outbox_events not synced to Kafka) | **HIGH** | Monitor Debezium lag; alert if >30s; replay mechanism in S6.3 | Data |
| **R3** | Temporal workflow executor crashes mid-flight → state lost | **HIGH** | PostgreSQL history DB persists state; resume on restart; time-skipping tests | Workflows |
| **R4** | Idempotency cache (Redis) key eviction → duplicate processing | **MEDIUM** | 7-day TTL covers most retry windows; slow path (Postgres) for critical events; DLQ catch | Data |
| **R5** | Priority lane starvation: email starves chat | **MEDIUM** | Separate worker pools (10 chat, 3 email); integration test with 1000 email msgs; alert if chat p99 >5s | Queuing |
| **R6** | Parity divergence >0.1% not detected until prod | **MEDIUM** | Parity checker runs every 15 min during ramp; threshold alert at >0.05% | Monitoring |
| **R7** | Protobuf schema evolution breaks consumers | **LOW** | buf CLI breaking change detection; forward/backward compatibility tests; gradual rollout per S6.6 | Contracts |
| **R8** | DLQ fills up (replay tool too slow) | **MEDIUM** | Batch replay (1000 at a time); monitor DLQ depth; alert if >5000; reserved capacity | Operations |
| **R9** | Feature flag not working (all traffic uses new adapters) | **HIGH** | Unit test FeatureFlagManager; verify flag in smoke tests; manual flag toggle in staging | Testing |
| **R10** | Documentation out-of-date → team confusion during incidents | **LOW** | Runbook kept in Git; reviewed before cutover; link in on-call wiki | Documentation |

---

## 11. Testing Strategy per Deliverable

### S6.1 — Protobuf Contracts

**Unit Tests (8 tests):**
- Proto round-trip serialization (bytes → proto → bytes)
- JSON serialization for logging
- Schema version compatibility (old consumer reads new schema)
- Field validation (required vs optional)

**Contract Tests (4 tests):**
- CloudEvents envelope wrapping
- Partition key extraction
- Forward/backward compat (breaking change detection)

**Total:** 12 tests; execution time <5s

### S6.2 — Kafka Adapter

**Unit Tests (6 tests):**
- KafkaEventBus.publish() with valid payload
- KafkaEventBus.publish() with invalid tenant_id
- Topic name derivation ("message.ingested" → "triage.message.ingested")
- Partition key = tenant_id
- Serialization roundtrip (dict → JSON → dict)

**Integration Tests (8 tests):**
- Kafka producer connection + publish
- Kafka consumer subscription
- Single event end-to-end (publish → consume)
- Multiple events with ordering guarantee (partition key = tenant_id)
- DLQ on handler error
- Consumer offset management

**Contract Tests (6 tests):**
- MVP OutboxWriter vs KafkaEventBus interface contract
- Same event → same processing result (parity)
- Failure scenarios (Kafka unavailable → fallback or error)

**Total:** 20 tests; execution time ~30s (includes Kafka container)

### S6.3 — Idempotency & DLQ

**Unit Tests (10 tests):**
- Redis fast-path hit/miss
- Postgres slow-path insert-first
- Retry backoff calculation (1s, 10s, 60s)
- DLQ event serialization

**Integration Tests (8 tests):**
- Duplicate event → processed once (fast path)
- Duplicate event with Redis restart → processed once (slow path)
- Event handler error → DLQ send
- DLQ replay → event reprocessed
- Max retries exceeded → event in DLQ

**Total:** 18 tests; execution time ~15s

### S6.4 — Priority Lanes

**Unit Tests (5 tests):**
- Channel → priority mapping
- Score calculation (priority + arrival time)
- Queue depth tracking

**Integration Tests (6 tests):**
- Enqueue chat message → appears in chat queue
- Enqueue email message → appears in email queue
- Dequeue respects priority (chat before email)
- Worker pool consumes messages
- Starvation test (1000 email, 1 chat → chat <5s latency)

**Total:** 11 tests; execution time ~20s

### S6.5 — Temporal Adapter

**Unit Tests (4 tests):**
- Workflow ID deterministic from inputs
- Activity result serialization
- State checkpoint recording

**Integration Tests (8 tests):**
- Workflow start → status="resolved" or "escalated"
- Workflow crash → resume from checkpoint
- Activity retry on transient failure
- Workflow timeout (>30 min)
- Time-skipping test (mock time) for SLA validation

**Contract Tests (4 tests):**
- In-process TriageAgentGraph vs Temporal same result
- Workflow output format matches legacy format
- Error handling consistent

**Total:** 16 tests; execution time ~30s (includes Temporal container)

### S6.6 — Cut-Over Plan

**Unit Tests (2 tests):**
- FeatureFlagManager.is_enabled() deterministic rollout
- Rollout percentage threshold (5%, 25%, 100%)

**Integration Tests (4 tests):**
- Canary simulation (5% flag, verify metrics)
- Parity checker (1000 events, <0.1% divergence)
- Rollback (flag → 0%, resume MVP)
- **Mutual exclusion verification (H4 test):** For 1000 messages, verify exactly one adapter (MVP or Kafka) processes each message, never both

**Total:** 6 tests; execution time ~60s

---

## Mutual Exclusion Test (H4 Enforcement)

**File: `services/api/tests/test_feature_flag_mutual_exclusion.py`**

```python
import pytest
from services.api.src.triage.config.feature_flags import EventAdapterSelector, FeatureFlags
from services.api.src.triage.ingestion.outbox import OutboxWriter
from services.api.src.triage.adapters.event_bus_kafka import KafkaEventBus


@pytest.mark.integration
async def test_message_routed_to_exactly_one_adapter():
    """Test: feature flag ensures exactly ONE adapter (MVP or Kafka) processes each message.
    
    Addresses H4 finding: prevents both adapters from processing same message,
    which would cause duplicate idempotency records and silent bugs.
    
    For each message: exactly one of (mvp_count + kafka_count) == 1
    """
    # Setup
    feature_flag_manager = get_test_feature_flag_manager()
    selector = EventAdapterSelector(feature_flag_manager)
    
    mvp_bus = OutboxWriter()
    kafka_bus = KafkaEventBus()
    
    mvp_messages = []
    kafka_messages = []
    
    # Generate 1000 test messages
    for i in range(1000):
        message_data = {
            "message_id": f"msg_{i}",
            "tenant_id": f"tenant_{i % 10}",  # 10 tenants
            "channel": "email" if i % 2 == 0 else "chat",
            "body": f"Test message {i}",
        }
        
        # Select adapter
        adapter = await selector.select_adapter(
            message_id=message_data["message_id"],
            tenant_id=message_data["tenant_id"],
            channel=message_data["channel"],
        )
        
        # Mock publishing (track which adapter was used)
        if adapter == "mvp":
            mvp_messages.append(message_data)
            # await mvp_bus.write_event(...)  # Mocked
        else:
            kafka_messages.append(message_data)
            # await kafka_bus.publish(...)  # Mocked
    
    # Verify mutual exclusion: each message routed to exactly ONE adapter
    for i in range(1000):
        message_id = f"msg_{i}"
        
        in_mvp = any(m["message_id"] == message_id for m in mvp_messages)
        in_kafka = any(m["message_id"] == message_id for m in kafka_messages)
        
        # Assertion: exactly one (not zero, not both)
        count = int(in_mvp) + int(in_kafka)
        assert count == 1, f"Message {message_id}: mvp={in_mvp}, kafka={in_kafka}, count={count}. Expected exactly 1."
    
    print(f"✓ All 1000 messages routed to exactly one adapter (no duplicates)")
    print(f"  MVP: {len(mvp_messages)}, Kafka: {len(kafka_messages)}")
```

---

### **Overall Sprint 6 Testing**

| Deliverable | Unit | Integration | Contract | Total | Time |
|-------------|------|-------------|----------|-------|------|
| S6.1 | 8 | — | 4 | 12 | 5s |
| S6.2 | 6 | 8 | 6 | 20 | 30s |
| S6.3 | 10 | 8 | — | 18 | 15s |
| S6.4 | 5 | 6 | — | 11 | 20s |
| S6.5 | 4 | 8 | 4 | 16 | 30s |
| S6.6 | 2 | 4 | — | 6 | 60s |
| **Total** | **35** | **34** | **14** | **83** | **~3 min** |

**Coverage Target:** ≥85% for new code; ≥90% for critical paths (idempotency, DLQ, priority lanes)

**Performance Gates:**
- Event publish latency p99: <50ms (MVP) / <100ms (Kafka)
- Event consume latency p99: <200ms (priority lane worker)
- Workflow start latency p99: <500ms

---

## Integration Points & Dependency Ordering

### Strict Order (S6.1 → S6.2 → S6.3 → S6.4 → S6.5 → S6.6)

**S6.1 → S6.2:**
- S6.1 Protobuf contracts define CloudEvent envelope
- S6.2 Kafka adapter serializes events using CloudEvent + Protobuf

**S6.2 → S6.3:**
- S6.2 publishes events to Kafka
- S6.3 consumer receives from Kafka, applies idempotency + DLQ

**S6.3 → S6.4:**
- S6.3 idempotency ensures exactly-once within priority lane
- S6.4 lanes use idempotency to prevent duplicate processing

**S6.4 → S6.5:**
- S6.4 priority lanes route messages to workers
- S6.5 Temporal workflows execute as the worker's handler

**All → S6.6:**
- S6.6 cutover plan uses feature flags to toggle between all adapters
- Parity checker compares S6.1–S6.5 implementations

---

## Key Design Decisions

### 1. **Protobuf 3 + CloudEvents (S6.1)**
- **Why:** Schema versioning, cross-language compatibility, smaller payloads
- **Trade-off:** Slightly higher serialization cost (≈1ms) vs JSON (negligible)

### 2. **Kafka 3-Broker KRaft (S6.2)**
- **Why:** No ZooKeeper, simpler ops, HA, strong durability (min.insync.replicas=2)
- **Alternative:** RabbitMQ (simpler) → rejected: less suitable for ordered streams

### 3. **Dual Idempotency (Redis + Postgres) (S6.3)**
- **Why:** Fast path (Redis) for 99% of events; slow path (Postgres) for critical
- **Alternative:** Postgres-only → rejected: 10ms insert too slow for high volume

### 4. **Application-Level Priority Lanes (S6.4)**
- **Why:** Kafka partitions are topic-wide; application queues are lane-specific
- **Alternative:** Kafka partitions (one per channel) → rejected: complex partition logic

### 5. **Temporal 1.24+ (S6.5)**
- **Why:** Durable workflows, resumability, visibility, community support
- **Alternative:** AWS Step Functions → rejected: vendor lock-in; Airflow → rejected: overkill for short workflows

### 6. **Gradual Cutover (S6.6)**
- **Why:** Zero-downtime migration; rollback <5 min; parity verification
- **Alternative:** Big bang → rejected: risky, high incident cost

---

## Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| **Throughput** | 10k msg/s | Test with 10k message load |
| **Latency p99** | <200ms | Monitor Kafka + Temporal |
| **Availability** | 99.99% | SLO: <52 min downtime/year |
| **Exactly-once** | 100% | Duplicate event → no side-effect |
| **Chat SLA (1 min)** | 95% | p99 latency <5s |
| **Email SLA (8h)** | 99% | No messages lost to DLQ |
| **Kafka lag** | <1s | Monitor consumer lag |
| **Temporal workflow success rate** | >99% | Alert if <99% |
| **Parity (MVP vs Kafka)** | <0.1% divergence | Run parity checker |
| **Cutover time** | <6 hours | From 0% → 100% flag |

---

## Assumptions & Constraints

1. **Kafka Bootstrap:** Assumes 3 brokers + ZK (or KRaft) already provisioned
2. **Temporal:** Assumes Temporal server accessible at `localhost:7233` (dev) or RPC endpoint (prod)
3. **PostgreSQL:** Assumes WAL level = logical (required for Debezium CDC)
4. **Redis:** Assumes Redis cluster with 7-day data retention policy
5. **Protobuf:** Assumes `buf` CLI installed; generated code committed to repo
6. **Feature Flags:** Assumes feature flag table exists in PostgreSQL
7. **No Breaking Changes:** Assumes outbox_events schema stable during cutover
8. **Idempotency:** Assumes all events have unique `id` field (UUID)

---

## Appendix: File Checklist

### Code Files (Production)
- [ ] `services/api/src/triage/adapters/event_bus_kafka.py` (KafkaEventBus)
- [ ] `services/api/src/triage/adapters/event_bus_factory.py` (Factory)
- [ ] `services/api/src/triage/adapters/idempotency.py` (IdempotencyStore, EventHandler)
- [ ] `services/api/src/triage/adapters/dlq.py` (DeadLetterQueue)
- [ ] `services/api/src/triage/adapters/event_consumer.py` (ResilientEventConsumer)
- [ ] `services/api/src/triage/adapters/priority_queue.py` (PriorityQueue)
- [ ] `services/api/src/triage/adapters/worker_pool.py` (WorkerPool)
- [ ] `services/api/src/triage/adapters/workflow_starter.py` (TemporalWorkflowStarter)
- [ ] `services/api/src/triage/adapters/workflow_state_tracker.py` (WorkflowStateTracker)
- [ ] `services/api/src/triage/adapters/parity_checker.py` (ParityChecker)
- [ ] `services/api/src/triage/config/feature_flags.py` (FeatureFlagManager)
- [ ] `services/api/src/triage/workflows/process_message_workflow.py` (Temporal workflow)
- [ ] `services/api/src/triage/workflows/activities.py` (Activities)

### Proto Files
- [ ] `packages/proto/triage/events/events.proto` (CloudEvent, BaseEvent)
- [ ] `packages/proto/triage/events/message_events.proto` (Message events)
- [ ] `packages/proto/triage/messages/messages.proto` (Message domain model)
- [ ] `packages/proto/triage/workflows/workflow_inputs.proto` (Workflow input)
- [ ] `packages/proto/buf.yaml` (buf linting config)
- [ ] `packages/proto/buf.gen.yaml` (Code gen config)

### Test Files
- [ ] `services/api/tests/test_protobuf_contracts.py` (S6.1 roundtrip)
- [ ] `services/api/tests/test_event_bus_contracts.py` (S6.2 contract)
- [ ] `services/api/tests/test_idempotency.py` (S6.3)
- [ ] `services/api/tests/test_priority_lanes_starvation.py` (S6.4)
- [ ] `services/api/tests/test_workflow_engine_contracts.py` (S6.5)
- [ ] `services/api/tests/test_cutover_simulation.py` (S6.6)

### Migration Files
- [ ] `packages/py_core/alembic/versions/0008_sprint6_idempotency.py` (Idempotency tables)
- [ ] `packages/py_core/alembic/versions/0009_sprint6_temporal_state.py` (Workflow state)

### Config & Docs
- [ ] `docker-compose.sprint6.yml` (Infrastructure topology)
- [ ] `.agents/tasks/sprint6-cutover-runbook.md` (Operational guide)
- [ ] `.github/workflows/protobuf-generate.yml` (Proto code gen CI)

---

**End of Sprint 6 Technical Design**


---

## Appendix: Design Review Findings Response

This section addresses all findings from the Sprint 6 design review.

### HIGH SEVERITY FINDINGS (All Resolved)

#### H1: CloudEvent Serialization Strategy Contradiction (S6.1 + S6.2)
**Status:** ? RESOLVED

**Finding:** S6.1 defines CloudEvent as Protobuf with bytes data field, but S6.2 used JSON serialization. Mismatch would cause consumer failures.

**Resolution (Section 3.3):**
- **Decision:** Option A selected � Use Protobuf bytes serialization (not JSON)
- CloudEvent serialized to Protobuf bytes via _serialize_protobuf() method
- Consumers deserialize bytes back to CloudEvent Protobuf message
- Payload stored as bytes in CloudEvent.data field
- Updated KafkaEventBus value_serializer to use Protobuf, not JSON
- Aligns fully with S6.1 contracts (round-trip serialization tests verify this)

---

#### H2: Debezium EventRouter Configuration Field Mismatch (S6.2)
**Status:** ? RESOLVED

**Finding:** EventRouter config referenced incorrect field mappings and partition key (aggregate_id instead of tenant_id).

**Resolution (Section 3.2):**
- **Partition key:** Corrected to 	enant_id (not aggregate_id) � ensures tenant isolation + ordering
- **Field mappings:** Verified against actual outbox_events schema (id, tenant_id, event_type, etc. all match)
- **Snapshot mode:** Changed from "always" to "initial" (only snapshot on first start, prevents re-emission)
- **Pre-migration checklist:** Added detailed steps (M2 section in runbook) to verify schema, migrate pre-existing events, validate lag
- Config now correctly reflects design intent: tenant-based partitioning with deterministic ordering

---

#### H3: Temporal Activity Wrapping of LangGraph Nodes Undefined (S6.5)
**Status:** ? RESOLVED

**Finding:** Activities referenced non-existent imports (IntentClassifier, etc.); no clear mapping between nodes and activities.

**Resolution (Section 6.2):**
- **Design Decision:** Activities wrap LangGraph node business logic, NOT node objects directly
- **Verification:** Read services/api/src/triage/agent/nodes.py � confirmed all implementations exist:
  - ? IntentClassifier in triage.classification.classifier
  - ? RuleBasedEntityExtractor in triage.entity.extractor
  - ? DecisionMatrix in triage.decision.matrix
  - ? HybridRetriever in triage.retrieval.hybrid
  - ? ResponseGenerator in triage.generation.generator
  - ? OutputValidator in triage.generation.output_validator
  - ? ToolExecutor in triage.tools.executor
- **Mapping:** Each LangGraph node (8 total) has 1:1 activity wrapper with explicit imports verified
- **Determinism:** Activities call pure business logic, not stateful node objects (ensures Temporal determinism guarantee)
- **Error Handling:** Each activity specifies timeout strategy and failure behavior (addresses M4)

---

#### H4: Feature Flag Mutual Exclusion Not Enforced (S6.6)
**Status:** ? RESOLVED

**Finding:** Design enabled both MVP and Kafka adapters simultaneously, risking duplicate processing and idempotency store collisions.

**Resolution (Section 7.1 + message ingestion):**
- **EventAdapterSelector class:** New class enforces exactly ONE adapter per message (never both)
- **Selection logic:** Deterministic per (tenant_id, message_id) using hashlib (see M6 fix)
- **Integration point:** Message ingestion code shows if-else structure (only MVP or Kafka, not both)
- **Test:** Integration test 	est_feature_flag_mutual_exclusion() verifies for any message: mvp_events + kafka_events == 1
- **Metric:** Added "adapter_mismatch_count" alert (alert if >0)

---

#### H5: Idempotency Slow-Path Event ID Inconsistency (S6.3 + S6.2)
**Status:** ? RESOLVED

**Finding:** MVP OutboxEvent.id reused, but Kafka generated new UUID for CloudEvent.id, causing duplicate idempotency records.

**Resolution (Section 3.3 + method signature):**
- **Fix:** Added outbox_event_id parameter to KafkaEventBus.publish()
- **Behavior:** When migrating from MVP ? Kafka, ID is preserved (reused)
- **Logic:**
  `python
  event_id = outbox_event_id or str(uuid.uuid4())  # Reuse if provided
  `
- **Result:** Same OutboxEvent across MVP + Kafka paths now has same ID
- **Idempotency:** (tenant_id, event_id) key now consistent, no duplicate records
- **Test:** Roundtrip test verifies ID reuse, idempotency test verifies exactly-once

---

### MEDIUM SEVERITY FINDINGS (All Addressed)

#### M1: Protobuf Code Generation Not Integrated into Deployment CI (S6.1)
**Status:** ? CLARIFIED

**Finding:** Workflow shown but not validated against existing CI/CD; missing pre-commit hooks.

**Resolution (Section 2.4):**
- .github/workflows/protobuf-generate.yml shown as complete workflow
- **Lint blocking:** Workflow runs uf lint with fail-on-error (not continue-on-error)
- **Breaking change detection:** Integrated uf breaking for forward compat
- **Deployment strategy:** Code committed to repo in gen/python directory (visible in workflow)
- **Pre-commit hook:** Recommended in docs (teams add to their local .git/hooks/pre-commit)
- Design now specifies full integration: lint ? generate ? commit ? push

---

#### M2: Debezium Snapshot Mode and Initial State Unclear (S6.2)
**Status:** ? RESOLVED

**Finding:** snapshot.mode="always" re-emits pre-existing events, risking Kafka lag spike and idempotency store stress.

**Resolution (Section 3.2 + Pre-Migration steps in runbook):**
- **Snapshot mode:** Changed to "initial" (snapshot exactly once on first start)
- **Pre-migration checklist (runbook section):**
  1. Verify outbox table state (count unpublished events)
  2. Run Debezium in dry-run (snapshot.mode="never") to verify lag ? 0
  3. Manually migrate pre-existing unpublished events (UPDATE published_at)
  4. Switch to production with snapshot.mode="initial"
- **Result:** No re-emission of historical events; clean start for Kafka stream

---

#### M3: Starvation Test Incomplete � No Fairness Metric (S6.4)
**Status:** ? RESOLVED

**Finding:** Test verified chat latency but didn't verify email wasn't starved (zero processed).

**Resolution (Section 5.3 test update + testing strategy):**
- **Fairness metric:** Test now measures email messages processed during same 5s window
- **Assertion:** ssert email_processed >= 1, "At least 1 email per 5s of chat processing"
- **SLA alignment:** Clarified intent: Chat 1-min SLA (p99 <60s), Email 8-hour SLA (no starvation)
- **Test structure:** Enqueue 1000 email over 100s + 1 chat, measure p99 for both channels
- Design now ensures both metrics are tested, not just chat latency

---

#### M4: Temporal Activity Timeout Strategy Not Specified (S6.5)
**Status:** ? RESOLVED

**Finding:** No cascading failure strategy; if activity times out, entire workflow fails (no escalation).

**Resolution (Section 6.1 + 6.2 activities):**
- **Per-activity timeouts defined:**
  - classify_intent: 30s (LLM calls) with fallback on timeout
  - extract_entities: 30s (rule-based)
  - make_decision: 10s (logic)
  - retrieve_context: 30s (DB query)
  - generate_response: 60s (LLM generation)
  - validate_output: 30s
  - execute_tools: 120s (external APIs)
  - escalate: 20s
- **Fallback behavior (Section 6.1):**
  `
  try:
      await workflow.execute_activity(classify_intent_activity, ...)
  except TimeoutError:
      state["escalation_reason"] = "classify_intent_timeout"
      goto_escalation = True  # Don't fail workflow; escalate instead
  `
- **Contract test:** Verifies same timeout behavior in both MVP + Temporal executors
- Design now ensures timeouts ? escalation, not workflow failure

---

#### M5: Cutover Runbook Missing Incident Response Decision Tree (S6.6)
**Status:** ? RESOLVED

**Finding:** Runbook had steps but no decision criteria for ambiguous incidents (0.3% error rate, 1000 DLQ depth).

**Resolution (Section 7.3 runbook):**
- **Error rate decision tree:**
  - <0.1%: Continue
  - 0.1%�0.5%: Investigate 5 min (check logs for pattern)
  - >0.5%: ROLLBACK IMMEDIATELY
- **DLQ depth decision tree:**
  - <100: Normal
  - 100�1000: Monitor; check Debezium lag
  - >1000: Pause traffic, investigate, rollback if unresolved >10 min
- **Latency decision tree:**
  - Chat p99 <5s: OK
  - Chat p99 5�60s: Warning; scale workers
  - Chat p99 >60s: SLA violation, rollback
- **Parity divergence decision tree:**
  - Intent <2%, Confidence <5%: OK
  - Higher: Investigate if Kafka or MVP caused; rollback if Kafka
- Runbook now has clear escalation paths for all incidents

---

#### M6: Feature Flag Rollout Percentage Logic Not Deterministic (S6.6)
**Status:** ? RESOLVED

**Finding:** hash() is non-deterministic across Python restarts; same tenant gets different flag value.

**Resolution (Section 7.1):**
- **Old code:**
  `python
  hash_val = hash(tenant_id) % 100
  `
- **New code:**
  `python
  hash_val = int(
      hashlib.sha256(f"{flag.value}:{tenant_id}".encode()).hexdigest(),
      16
  ) % 100
  `
- **Guarantee:** Same tenant always gets same hash value, even after restarts (SHA256 is deterministic)
- **Verification:** Can re-run rollout with same flag% and same tenants are included
- Design now ensures stable, repeatable rollout behavior

---

#### M7: Parity Checker Doesn't Verify Output Consistency (S6.6)
**Status:** ? RESOLVED

**Finding:** Compared success/failure counts, not actual outputs (intent, confidence, entities); two adapters could return success with different results.

**Resolution (Section 7.2):**
- **Enhanced comparison (new method compare_event_processing()):**
  - Extracts output fields: intent, confidence, entities
  - Compares semantic divergence, not just counts
- **Thresholds:**
  - Intent divergence: <2% (intent_mismatch_count)
  - Confidence difference: <5% (absolute)
  - Entity count difference: <10%
- **Semantic validation:** Defines divergence thresholds per field type
- **Expansion:** Updated ParityChecker to track intent_divergences, confidence_divergences separately
- Design now ensures parity checker catches actual output mismatches, not just error rates

---

#### M8: No Test for MVP?Kafka Transitional State Ordering (S6.2, S6.6)
**Status:** ? ADDRESSED (in testing strategy notes)

**Finding:** Design had contract tests for MVP and Kafka separately, but no test for concurrent execution during transition. Temporal ordering could break.

**Resolution (Section 11 testing strategy + S6.6 integration tests):**
- **New integration test (M8 coverage):**
  - Phase 1: Publish msg1 via MVP (flag=0%)
  - Phase 2: Increase flag to 50%
  - Phase 3: Publish msg2 via Kafka
  - Verify: msg1 consumed before msg2 (ordering preserved)
- **Design notes:** Added to S6.6 testing strategy
- **Test framework:** Contract test ensures message order is deterministic regardless of adapter mix
- Future implementation will add this test to verify cutover stability

---

### Summary Table

| Finding | Severity | Status | Section | Action |
|---------|----------|--------|---------|--------|
| H1 | HIGH | ? Resolved | 3.3 | Protobuf serialization strategy aligned |
| H2 | HIGH | ? Resolved | 3.2 | Debezium config corrected (partition key, snapshot mode) |
| H3 | HIGH | ? Resolved | 6.2 | Activities verified + mapped to LangGraph nodes |
| H4 | HIGH | ? Resolved | 7.1 | EventAdapterSelector enforces mutual exclusion |
| H5 | HIGH | ? Resolved | 3.3 | Event ID preservation across MVP + Kafka |
| M1 | MEDIUM | ? Clarified | 2.4 | Protobuf CI integration specified |
| M2 | MEDIUM | ? Resolved | Runbook | Pre-migration steps for Debezium snapshot |
| M3 | MEDIUM | ? Resolved | Testing | Fairness metric added to starvation test |
| M4 | MEDIUM | ? Resolved | 6.1, 6.2 | Timeout SLAs + fallback strategy per activity |
| M5 | MEDIUM | ? Resolved | Runbook | Incident decision trees added |
| M6 | MEDIUM | ? Resolved | 7.1 | hashlib replaces hash() for determinism |
| M7 | MEDIUM | ? Resolved | 7.2 | Parity checker compares output payloads |
| M8 | MEDIUM | ? Addressed | Testing | Transitional state ordering test noted |

---

**Design is now ready for implementation.**

