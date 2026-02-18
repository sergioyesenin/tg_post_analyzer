from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_session
from db.models import Report
from schemas.report import ReportOut

router = APIRouter()

@router.get("/{post_id}", response_model=ReportOut)
async def get_report(post_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Report).where(Report.post_id == post_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return report
