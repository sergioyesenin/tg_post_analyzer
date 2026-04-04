from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text


def main() -> None:
    url = os.getenv("DB_URL", "").replace("+asyncpg", "+psycopg2")
    if not url:
        raise SystemExit("DB_URL is not set")

    eng = create_engine(url)
    conn = eng.connect()
    try:
        now = datetime.now(timezone.utc)

        heartbeat = conn.execute(
            text("SELECT key, value_json FROM app_settings WHERE key = 'runtime.ai_pipeline'")
        ).fetchone()
        print("runtime.ai_pipeline heartbeat:", heartbeat[1] if heartbeat else None)

        running = list(
            conn.execute(
                text(
                    "SELECT id, type, status, locked_by, locked_at, heartbeat_at "
                    "FROM jobs WHERE status='running' AND type IN "
                    "('build_post_report','build_post_report_batch','build_event_report','build_process_report') "
                    "ORDER BY locked_at DESC LIMIT 10"
                )
            )
        )
        print("AI running jobs:", running)

        pending_due = conn.execute(
            text(
                "SELECT COUNT(*) FROM jobs "
                "WHERE status='pending' "
                "AND type IN ('build_post_report','build_post_report_batch','build_event_report','build_process_report') "
                "AND COALESCE(retry_at, run_at) <= :now"
            ),
            {"now": now},
        ).scalar()
        print("AI pending due:", int(pending_due or 0))
    finally:
        conn.close()
        eng.dispose()


if __name__ == "__main__":
    main()
