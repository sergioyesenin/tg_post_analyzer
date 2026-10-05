from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JobResultBase(BaseModel):
    """Базовая схема результата job.
    
    extra="allow" — намеренно, чтобы не сломать существующие данные
    и оставить возможность добавлять диагностические поля без
    немедленного обновления схемы.
    """
    model_config = ConfigDict(extra="allow")
    status: str


class PostReportJobResult(JobResultBase):
    post_id: int
    report_id: int | None = None


class EventReportJobResult(JobResultBase):
    event_id: int
    report_id: int | None = None


class ProcessReportJobResult(JobResultBase):
    process_id: int
    report_id: int | None = None


class PostReportBatchJobResult(JobResultBase):
    """Passive AI worker не диспатчит batch, но должен фиксировать причину."""
    reason: str
    message: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class CommentRefreshJobResult(JobResultBase):
    comments_saved: int | None = None


class BuildPostLinksJobResult(JobResultBase):
    post_id: int
    links_verified: int = 0
    links_proposed: int = 0
    links_rejected: int = 0
    candidates_checked: int = 0
    verify_checked: int = 0
    critic_checked: int = 0
    queued_for_review: int = 0


class RebuildEventsJobResult(JobResultBase):
    rebuilt_events: int


class RebuildProcessesJobResult(JobResultBase):
    rebuilt_process_edges: int


class AddChannelJobResult(JobResultBase):
    channel_id: int
    username: str
    title: str | None = None


class MaintenanceJobResult(JobResultBase):
    """Архивация/retention — динамический payload, оставляем extra=allow."""
    pass


class DeferredJobResult(JobResultBase):
    reason: str
    dependencies: list[dict[str, Any]] = Field(default_factory=list)


class FailedJobResult(JobResultBase):
    reason: str
    error: str | None = None