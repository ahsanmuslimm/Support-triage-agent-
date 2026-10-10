"""Factory fixtures for generating test data using factory_boy."""

import datetime
from uuid import UUID, uuid4

try:
    import factory
    from factory.fuzzy import FuzzyChoice

    FACTORY_BOY_AVAILABLE = True
except ImportError:
    FACTORY_BOY_AVAILABLE = False


if FACTORY_BOY_AVAILABLE:

    class TenantFactory(factory.Factory):
        """Factory for generating Tenant test data."""

        class Meta:
            model = dict

        tenant_id = factory.LazyFunction(uuid4)
        name = factory.Faker("company")
        created_at = factory.LazyFunction(datetime.datetime.utcnow)

    class CustomerFactory(factory.Factory):
        """Factory for generating Customer test data."""

        class Meta:
            model = dict

        customer_id = factory.LazyFunction(uuid4)
        tenant_id = factory.SubFactory(TenantFactory, tenant_id=factory.SelfAttribute("..tenant_id")).get("tenant_id") if False else factory.LazyFunction(uuid4)
        email = factory.Faker("email")
        name = factory.Faker("name")
        created_at = factory.LazyFunction(datetime.datetime.utcnow)

    class ConversationFactory(factory.Factory):
        """Factory for generating Conversation test data."""

        class Meta:
            model = dict

        conversation_id = factory.LazyFunction(uuid4)
        customer_id = factory.LazyFunction(uuid4)
        tenant_id = factory.LazyFunction(uuid4)
        subject = factory.Faker("sentence")
        status = factory.Faker("random_element", elements=["open", "resolved", "escalated"])
        created_at = factory.LazyFunction(datetime.datetime.utcnow)

    class MessageFactory(factory.Factory):
        """Factory for generating Message test data."""

        class Meta:
            model = dict

        message_id = factory.LazyFunction(uuid4)
        conversation_id = factory.LazyFunction(uuid4)
        sender = factory.Faker("name")
        body = factory.Faker("paragraph")
        timestamp = factory.LazyFunction(datetime.datetime.utcnow)


else:
    # Fallback: simple dictionary factories if factory_boy is not available
    class TenantFactory:
        """Fallback factory for Tenant (dict-based)."""

        @staticmethod
        def create(**kwargs) -> dict:
            """Create a tenant dict."""
            data = {
                "tenant_id": str(kwargs.get("tenant_id", uuid4())),
                "name": kwargs.get("name", "Test Tenant"),
                "created_at": kwargs.get("created_at", datetime.datetime.utcnow()),
            }
            data.update(kwargs)
            return data

    class CustomerFactory:
        """Fallback factory for Customer (dict-based)."""

        @staticmethod
        def create(**kwargs) -> dict:
            """Create a customer dict."""
            data = {
                "customer_id": str(kwargs.get("customer_id", uuid4())),
                "tenant_id": str(kwargs.get("tenant_id", uuid4())),
                "email": kwargs.get("email", "customer@example.com"),
                "name": kwargs.get("name", "Test Customer"),
                "created_at": kwargs.get("created_at", datetime.datetime.utcnow()),
            }
            data.update(kwargs)
            return data

    class ConversationFactory:
        """Fallback factory for Conversation (dict-based)."""

        @staticmethod
        def create(**kwargs) -> dict:
            """Create a conversation dict."""
            data = {
                "conversation_id": str(kwargs.get("conversation_id", uuid4())),
                "customer_id": str(kwargs.get("customer_id", uuid4())),
                "tenant_id": str(kwargs.get("tenant_id", uuid4())),
                "subject": kwargs.get("subject", "Test Conversation"),
                "status": kwargs.get("status", "open"),
                "created_at": kwargs.get("created_at", datetime.datetime.utcnow()),
            }
            data.update(kwargs)
            return data

    class MessageFactory:
        """Fallback factory for Message (dict-based)."""

        @staticmethod
        def create(**kwargs) -> dict:
            """Create a message dict."""
            data = {
                "message_id": str(kwargs.get("message_id", uuid4())),
                "conversation_id": str(kwargs.get("conversation_id", uuid4())),
                "sender": kwargs.get("sender", "Test Sender"),
                "body": kwargs.get("body", "Test message body"),
                "timestamp": kwargs.get("timestamp", datetime.datetime.utcnow()),
            }
            data.update(kwargs)
            return data


__all__ = ["TenantFactory", "CustomerFactory", "ConversationFactory", "MessageFactory"]
