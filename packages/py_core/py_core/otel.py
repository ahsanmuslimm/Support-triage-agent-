"""OpenTelemetry instrumentation and tracing setup."""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_otel(service_name: str) -> None:
    """Configure OpenTelemetry with OTLP exporter.

    Args:
        service_name: Name of the service for tracing.
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Create tracer provider
    tracer_provider = TracerProvider()

    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global provider
    trace.set_tracer_provider(tracer_provider)


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance.

    Args:
        name: Name of the tracer (typically __name__).

    Returns:
        trace.Tracer: Tracer instance.
    """
    return trace.get_tracer(name)


def record_exception(
    span: trace.Span, exc: Exception, attributes: Optional[dict] = None
) -> None:
    """Record an exception on a span, filtering PII.

    Args:
        span: Active span.
        exc: Exception to record.
        attributes: Additional attributes to add to the span.
    """
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)

    # Record exception
    span.record_exception(exc)
