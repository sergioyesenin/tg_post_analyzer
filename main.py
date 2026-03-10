from __future__ import annotations

import warnings

from scripts.run_telegram_pipeline import _build_parser, main as _canonical_main, main_async as _canonical_main_async


async def run_today_ingestion() -> None:
    warnings.warn(
        "`main.run_today_ingestion()` is deprecated. Use `python scripts/run_telegram_pipeline.py`.",
        DeprecationWarning,
        stacklevel=2,
    )
    args = _build_parser().parse_args([])
    await _canonical_main_async(args)


def main() -> None:
    warnings.warn(
        "`python main.py` is deprecated. Use `python scripts/run_telegram_pipeline.py`.",
        DeprecationWarning,
        stacklevel=2,
    )
    _canonical_main()


if __name__ == "__main__":
    main()
