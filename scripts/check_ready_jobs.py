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
        rows = list(
            conn.execute(
                text(
                    "SELECT id, type, status, retry_at, run_at "
                    "FROM jobs "
                    "WHERE status='pending' AND COALESCE(retry_at, run_at) <= :now "
                    "ORDER BY priority, id"
                ),
                {"now": now},
            )
        )
        print(rows[:10])
    finally:
        conn.close()
        eng.dispose()


if __name__ == "__main__":
    main()
