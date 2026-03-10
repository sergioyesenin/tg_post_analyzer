from __future__ import annotations

import asyncio
import warnings

from main import run_today_ingestion


async def main() -> None:
    warnings.warn(
        "`parse_today.py` is deprecated. Use `python scripts/run_telegram_pipeline.py`.",
        DeprecationWarning,
        stacklevel=2,
    )
    await run_today_ingestion()


if __name__ == "__main__":
    asyncio.run(main())
