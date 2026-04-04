from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from deps import get_session, require_roles
from db.models import Post, Channel, Comment
from schemas.post import PostCardOut, PostDetailOut
from schemas.comment import CommentOut
from services.auth import AuthUser
from services.orchestration import enqueue_comment_refresh_job
from services.settings_store import get_setting

router = APIRouter()


def _job_accepted_response(*, job_id: int, job_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=jsonable_encoder(
            {
                "status": "queued",
                "job_id": job_id,
                "job_type": job_type,
                "status_url": f"/api/jobs/{job_id}",
                "result_url": f"/api/jobs/{job_id}/result",
            }
        ),
    )

@router.get("/top", response_model=list[PostCardOut])
async def top_posts(
    date_from: datetime,
    date_to: datetime,
    limit: int | None = None,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    if limit is None:
        api_settings = await get_setting(session, "api")
        limit = int(api_settings.get("top_posts_default_limit", 20))
    stmt = (
        select(Post)
        .join(Channel)
        .where(Post.date >= date_from)
        .where(Post.date <= date_to)
        .order_by(desc(Post.comments_count))
        .limit(limit)
        .options(selectinload(Post.channel))
    )

    result = await session.execute(stmt)
    posts = result.scalars().all()

    return [
        PostCardOut(
            id=p.id,
            channel_id=p.channel_id,
            channel_username=p.channel.username,
            date=p.date,
            text_preview=(p.text.splitlines()[0] if p.text else None),
            comments_count=p.comments_count,
            views=p.views,
            involvement=p.involvement,
        )
        for p in posts
    ]


@router.get("/{post_id}", response_model=PostDetailOut)
async def get_post(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    post = (await session.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    result = await session.execute(
        select(Comment).where(Comment.post_id == post_id)
    )
    return result.scalars().all()

@router.post("/{post_id}/comments/update")
async def update_comments(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    post = (await session.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    job = await enqueue_comment_refresh_job(session, post_id=post_id, source="api")
    await session.commit()
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue refresh_comments job")
    return _job_accepted_response(job_id=job.id, job_type=job.type)
