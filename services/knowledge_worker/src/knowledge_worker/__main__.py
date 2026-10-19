"""Entry point: python -m knowledge_worker."""

import asyncio

from knowledge_worker import run_forever

if __name__ == "__main__":
    asyncio.run(run_forever())
