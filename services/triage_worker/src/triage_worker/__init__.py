"""Triage worker: consumes message.ingested outbox events and runs triage."""

from .worker import run_forever

__all__ = ["run_forever"]
