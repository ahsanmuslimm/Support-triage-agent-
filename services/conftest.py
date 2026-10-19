"""Shared path setup: make the api package (``triage``) importable to all tests under services/."""

import sys
from pathlib import Path

SRC = Path(__file__).parent / "api" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
