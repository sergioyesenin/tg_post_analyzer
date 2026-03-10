from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import posts
from db.models import Comment, Post
from deps import get_current_user
from services.auth import AuthUser


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, *, existing_post_ids: set[int], comments_by_post_id: dict[int, list[object]] | None = None):
        self._existing_post_ids = existing_post_ids
        self._comments_by_post_id = comments_by_post_id or {}

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        params = stmt.compile().params
        post_id = next(iter(params.values()))

        if entity is Post:
            if post_id in self._existing_post_ids:
                return _FakeResult(one=SimpleNamespace(id=post_id))
            return _FakeResult(one=None)

        if entity is Comment:
            return _FakeResult(rows=self._comments_by_post_id.get(post_id, []))

        raise AssertionError(f"Unexpected entity in statement: {entity}")


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(posts.router, prefix="/api/posts")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("viewer",))

    app.dependency_overrides[posts.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_get_comments_returns_404_for_missing_post():
    client = _build_client(_FakeSession(existing_post_ids=set()))

    response = client.get("/api/posts/999/comments")

    assert response.status_code == 404
    assert response.json() == {"detail": "Post not found"}


def test_get_comments_returns_200_and_empty_list_for_existing_post_without_comments():
    client = _build_client(_FakeSession(existing_post_ids={42}, comments_by_post_id={42: []}))

    response = client.get("/api/posts/42/comments")

    assert response.status_code == 200
    assert response.json() == []


def test_get_comments_keeps_success_response_shape_for_existing_post_with_comments():
    comment = SimpleNamespace(
        id=7,
        post_id=42,
        tg_message_id=701,
        parent_tg_message_id=None,
        parent_comment_id=None,
        thread_root_tg_message_id=None,
        depth=0,
        text="hello",
        date=datetime(2026, 3, 8, tzinfo=timezone.utc),
    )
    client = _build_client(_FakeSession(existing_post_ids={42}, comments_by_post_id={42: [comment]}))

    response = client.get("/api/posts/42/comments")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 7,
            "post_id": 42,
            "tg_message_id": 701,
            "parent_tg_message_id": None,
            "parent_comment_id": None,
            "thread_root_tg_message_id": None,
            "depth": 0,
            "text": "hello",
            "date": "2026-03-08T00:00:00Z",
        }
    ]
