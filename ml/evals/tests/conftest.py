"""Pytest configuration and fixtures for evaluation tests."""

import json
import pytest


def pytest_addoption(parser):
    """Add custom CLI options for eval tests."""
    parser.addoption(
        "--eval",
        action="store_true",
        default=False,
        help="Run evaluation tests (default: skip)",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip eval tests unless --eval is passed."""
    if not config.getoption("--eval"):
        skip_eval = pytest.mark.skip(reason="pass --eval to run evaluation tests")
        for item in items:
            if "eval" in item.keywords:
                item.add_marker(skip_eval)


@pytest.fixture
def intents_dataset():
    """Load intent classification golden dataset."""
    return _load_jsonl("ml/evals/golden/intents_v0.jsonl")


@pytest.fixture
def entities_dataset():
    """Load entity extraction golden dataset."""
    return _load_jsonl("ml/evals/golden/entities_v0.jsonl")


@pytest.fixture
def rag_dataset():
    """Load RAG retrieval golden dataset."""
    return _load_jsonl("ml/evals/golden/rag_v0.jsonl")


@pytest.fixture
def guards_dataset():
    """Load guardrail enforcement golden dataset."""
    return _load_jsonl("ml/evals/golden/guards_v0.jsonl")


def _load_jsonl(path: str) -> list[dict]:
    """Load a JSONL file and return list of dictionaries."""
    import os

    full_path = os.path.join(os.path.dirname(__file__), "..", path.replace("ml/evals/", ""))
    data = []
    if os.path.exists(full_path):
        with open(full_path, "r") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    return data


@pytest.fixture
def fake_llm():
    """Provide a fake LLM for deterministic testing."""
    from py_core.testing import FakeLLM

    return FakeLLM()


@pytest.fixture
def fake_clock():
    """Provide a fake clock for time-dependent tests."""
    from py_core.testing import FakeClock

    return FakeClock()


@pytest.fixture
def event_bus():
    """Provide an in-memory event bus for testing."""
    from py_core.testing import InMemoryEventBus

    return InMemoryEventBus()
