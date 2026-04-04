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
        result = conn.execute(
            text(
                "UPDATE jobs "
                "SET status='pending', locked_by=NULL, locked_at=NULL, heartbeat_at=NULL, retry_at=:now "
                "WHERE status='running' "
                "AND type IN ('build_post_report','build_post_report_batch','build_event_report','build_process_report')"
            ),
            {"now": now},
        )
        conn.commit()
        print("reset", int(result.rowcount or 0))
    finally:
        conn.close()
        eng.dispose()


if __name__ == "__main__":
    main()
