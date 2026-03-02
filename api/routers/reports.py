from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import TgReportProject
from deps import get_session
from db.models import Report, Post, Comment, Channel
from schemas.report import ReportOut
from services.ingest import upsert_report

router = APIRouter()
report_project = TgReportProject(
    llm_model="ollama/llama3:8b-instruct-q4_K_M",
)

@router.get("/{post_id}", response_model=ReportOut)
async def get_report(post_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Report).where(Report.post_id == post_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return report


@router.post("/{post_id}/update", response_model=ReportOut)
async def update_report(post_id: int, session: AsyncSession = Depends(get_session)):
    post_result = await session.execute(
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = post_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Post not found")

    post, channel = row

    comments_result = await session.execute(
        select(
            Comment.tg_message_id,
            Comment.parent_tg_message_id,
            Comment.thread_root_tg_message_id,
            Comment.depth,
            Comment.date,
            Comment.text,
        )
        .where(Comment.post_id == post_id)
        .order_by(Comment.date.asc(), Comment.id.asc())
    )
    thread_comments: list[dict] = []
    comments: list[str] = []
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text in comments_result.all():
        if not text or not text.strip():
            continue
        comments.append(text)
        normalized_parent_id = parent_tg_message_id
        if thread_root_tg_message_id is not None and parent_tg_message_id == thread_root_tg_message_id:
            normalized_parent_id = None
        thread_comments.append(
            {
                "id": tg_message_id,
                "parent_id": normalized_parent_id,
                "depth": depth,
                "date": date.isoformat() if date is not None else None,
                "text": text,
            }
        )

    channel_label = f"@{channel.username}" if channel.username else f"channel:{channel.id}"
    status = "ready"
    try:
        content = await report_project.generate_report(
            channel=channel_label,
            post_id=post.id,
            published_at_iso=post.date.isoformat(),
            post_text=post.text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=post.views,
        )
    except Exception as e:
        status = "failed"
        content = f"STATUS: FAILED\nREASON: {e!r}"

    report = await upsert_report(
        session,
        post_id=post_id,
        status=status,
        content=content,
    )
    await session.commit()

    return report
