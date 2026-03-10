from __future__ import annotations

import asyncio
import warnings

from db.models import Job
from services.jobs import JobType
from services.pipeline_runtime import _clamp_positive_int, is_session_locked_error, with_session_lock_retry
from scripts.run_telegram_pipeline import main as _canonical_main


def _split_locked_jobs_by_type(jobs: list[Job]) -> tuple[list[Job], list[Job]]:
    collect_comments_jobs: list[Job] = []
    other_jobs: list[Job] = []
    for job in jobs:
        if job.type == JobType.COLLECT_COMMENTS:
            collect_comments_jobs.append(job)
        else:
            other_jobs.append(job)
    return collect_comments_jobs, other_jobs


def main() -> None:
    warnings.warn(
        "`scripts/pipeline.py` is deprecated. Use `python scripts/run_telegram_pipeline.py`.",
        DeprecationWarning,
        stacklevel=2,
    )
    _canonical_main()


if __name__ == "__main__":
    main()
