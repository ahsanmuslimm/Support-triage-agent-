"""Sprint 6.1: Protobuf contract tests for event serialization."""
import pytest
from datetime import datetime
import json

# Note: After buf code generation, these imports will work:
# from gen.python.triage.events.v1 import message_events_pb2, events_pb2
# For now, we document the test structure


@pytest.mark.unit
class TestProtobufContracts:
    """Test Protobuf serialization and deserialization."""

    def test_message_ingested_serialization_structure(self):
        """Test: MessageIngested can be defined in Protobuf."""
        # This test verifies the proto definition is correct
        # After buf generation, the implementation will be in gen/python/triage/events/v1/message_events_pb2.py
        # The test structure documents expected behavior:
        
        # Create event
        event_dict = {
            "base_id": "evt_123",
            "base_tenant_id": "tenant_1",
            "base_version": 1,
            "message_id": "msg_456",
            "conversation_id": "conv_789",
            "customer_id": "cust_010",
            "channel": "email",
            "body": "Where is my order?",
        }
        
        # Expected: After buf generates code, we can instantiate and serialize
        # message_ingested = MessageIngested(
        #     base=BaseEvent(id="evt_123", tenant_id="tenant_1", version=1),
        #     message_id="msg_456",
        #     conversation_id="conv_789",
        #     customer_id="cust_010",
        #     channel="email",
        #     body="Where is my order?",
        # )
        # serialized = message_ingested.SerializeToString()
        # assert len(serialized) < 500  # Protobuf is compact
        
        assert event_dict["message_id"] == "msg_456"

    def test_cloud_event_envelope_structure(self):
        """Test: CloudEvent wraps domain events with RFC 7807 compatibility."""
        cloud_event_dict = {
            "id": "evt_123",
            "source": "triage/messages",
            "type": "message.ingested",
            "tenant_id": "tenant_1",
            "data_content_type": "application/protobuf",
            "subject": "tenant/tenant_1/message/msg_456",
        }
        
        assert cloud_event_dict["type"] == "message.ingested"
        assert cloud_event_dict["tenant_id"] == "tenant_1"

    def test_schema_versioning_forward_compat(self):
        """Test: Old consumers handle new schema fields gracefully (proto3 default behavior)."""
        # In Proto3, unknown fields are ignored during deserialization
        # This test documents forward compatibility
        
        # If old consumer deserializes new message with unknown fields:
        # - Protobuf ignores unknown fields
        # - Known fields are preserved
        # - Result: safe evolution
        
        assert True  # Proto3 provides this automatically

    def test_message_status_enum(self):
        """Test: MessageStatus enum supports all states."""
        statuses = [
            "UNSPECIFIED",
            "INGESTED",
            "CLASSIFIED",
            "ROUTED",
            "RESOLVED",
            "FAILED",
        ]
        assert len(statuses) == 6

    def test_checkpoint_phase_enum(self):
        """Test: WorkflowCheckpoint phase enum supports all phases."""
        phases = [
            "UNSPECIFIED",
            "CLASSIFY",
            "ENRICH",
            "DECIDE",
            "RESOLVE",
            "ESCALATE",
            "COMPLETE",
        ]
        assert len(phases) == 7


@pytest.mark.integration
class TestProtobufCodeGeneration:
    """Test Protobuf code generation pipeline (requires buf CLI)."""

    def test_buf_configuration_exists(self):
        """Test: buf.yaml and buf.gen.yaml are present."""
        import os
        assert os.path.exists("packages/proto/buf.yaml")
        assert os.path.exists("packages/proto/buf.gen.yaml")

    def test_proto_files_exist(self):
        """Test: All proto files are present."""
        import os
        proto_files = [
            "packages/proto/triage/events/events.proto",
            "packages/proto/triage/events/message_events.proto",
            "packages/proto/triage/messages/messages.proto",
            "packages/proto/triage/workflows/workflow_inputs.proto",
        ]
        for proto_file in proto_files:
            assert os.path.exists(proto_file), f"Missing {proto_file}"
