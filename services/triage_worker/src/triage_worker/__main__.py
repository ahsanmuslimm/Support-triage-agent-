"""Entry point: python -m triage_worker."""

import asyncio

from triage_worker import run_forever

if __name__ == "__main__":
    asyncio.run(run_forever())
