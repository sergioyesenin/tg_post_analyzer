from datetime import datetime, timezone

import pytest

from api.routers import auth as auth_router
from db.models import Channel, Job, Post, Role, User, UserRole
from services.auth import hash_password


def _seed_report_batch_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Role(id=1, name="analyst"))
        session.add(
            User(
                id=1,
                username="analyst",
                email="analyst@example.com",
                full_name="Analyst",
                password_hash=hash_password("AnalystPass123!"),
                is_active=True,
                is_local=True,
            )
        )
        session.add(UserRole(user_id=1, role_id=1))
        session.add(Channel(id=1, username="chan_one", title="Chan One", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=1001,
                date=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                created_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                text="Integration test post",
                comments_count=7,
                analyzer_version="v1",
            )
        )
        session.commit()


@pytest.mark.integration
def test_report_batch_enqueue_and_job_status_against_real_db(
    integration_client,
    integration_sync_session_factory,
) -> None:
    _seed_report_batch_fixture(integration_sync_session_factory)
    analyst_token = auth_router.create_access_token(user_id=1, username="analyst", roles=["analyst"])

    enqueue = integration_client.post(
        "/api/reports/posts/generate-by-filter?channel_ids=1&categories=news&min_comments=5&limit=25",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )

    assert enqueue.status_code == 202
    payload = enqueue.json()
    assert payload["job_type"] == "build_post_report_batch"
    job_id = payload["job_id"]

    status_response = integration_client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {analyst_token}"})

    assert status_response.status_code == 200
    assert status_response.json()["type"] == "build_post_report_batch"

    with integration_sync_session_factory() as session:
        job = session.get(Job, job_id)

        assert job is not None
        assert job.payload_json["filters"]["channel_ids"] == [1]
        assert job.payload_json["filters"]["categories"] == ["news"]
