from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DashboardWarning(BaseModel):
    code: str
    message: str


class DashboardSortMeta(BaseModel):
    by: str
    order: str


class DashboardMeta(BaseModel):
    sort: DashboardSortMeta | None = None
    supported_sorts: list[str] = Field(default_factory=list)


class PostsDashboardFilters(BaseModel):
    date_from: datetime
    date_to: datetime
    limit: int
    channel_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    min_comments: int | None = None
    report_status: list[str] = Field(default_factory=list)
    sort_by: str
    sort_order: str


class PostsDashboardSummary(BaseModel):
    posts_count: int
    total_comments: int
    avg_involvement: float | None = None
    channels_count: int
    reports_ready: int
    reports_missing: int
    reports_pending: int
    reports_failed: int


class PostsDashboardItem(BaseModel):
    post_id: int
    channel_id: int
    channel_username: str | None = None
    channel_title: str | None = None
    channel_category: str | None = None
    date: datetime
    text_preview: str | None = None
    comments_count: int
    views: int | None = None
    involvement: float | None = None
    report_status: str
    has_report: bool
    comments_refresh_available: bool
    links_count: int | None = None


class PostsDashboardResponse(BaseModel):
    mode: str = "posts"
    generated_at: datetime
    partial: bool
    warnings: list[DashboardWarning] = Field(default_factory=list)
    filters_applied: PostsDashboardFilters
    summary: PostsDashboardSummary
    items: list[PostsDashboardItem]
    meta: DashboardMeta


class EventsDashboardFilters(BaseModel):
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int
    status: list[str] = Field(default_factory=list)
    channel_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    min_comments: int | None = None
    sort_by: str
    sort_order: str


class EventsDashboardSummary(BaseModel):
    events_count: int
    total_linked_posts: int
    total_comments: int
    avg_involvement: float | None = None
    draft_reports: int
    ready_reports: int
    failed_reports: int


class DashboardChannelRef(BaseModel):
    channel_id: int
    channel_username: str | None = None


class EventsDashboardItem(BaseModel):
    event_id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    comments_count: int
    involvement: float | None = None
    posts_count: int
    post_ids: list[int] = Field(default_factory=list)
    root_post_id: int | None = None
    channels: list[DashboardChannelRef] = Field(default_factory=list)
    report_status: str
    graph_ready: bool


class EventsDashboardResponse(BaseModel):
    mode: str = "events"
    generated_at: datetime
    partial: bool
    warnings: list[DashboardWarning] = Field(default_factory=list)
    filters_applied: EventsDashboardFilters
    summary: EventsDashboardSummary
    items: list[EventsDashboardItem]
    meta: DashboardMeta


class ProcessesDashboardFilters(BaseModel):
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int
    status: list[str] = Field(default_factory=list)
    min_comments: int | None = None
    sort_by: str
    sort_order: str


class ProcessesDashboardSummary(BaseModel):
    processes_count: int
    total_events: int
    total_comments: int
    avg_involvement: float | None = None
    draft_reports: int
    failed_reports: int


class ProcessesDashboardItem(BaseModel):
    process_id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    comments_count: int
    involvement: float | None = None
    events_count: int
    event_ids: list[int] = Field(default_factory=list)
    report_status: str
    graph_ready: bool


class ProcessesDashboardResponse(BaseModel):
    mode: str = "processes"
    generated_at: datetime
    partial: bool
    warnings: list[DashboardWarning] = Field(default_factory=list)
    filters_applied: ProcessesDashboardFilters
    summary: ProcessesDashboardSummary
    items: list[ProcessesDashboardItem]
    meta: DashboardMeta


class EventGraphEvent(BaseModel):
    event_id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    report_status: str
    posts_count: int
    comments_count: int
    involvement: float | None = None


class EventGraphNode(BaseModel):
    post_id: int
    channel_id: int
    channel_username: str | None = None
    date: datetime
    text_preview: str | None = None
    comments_count: int
    views: int | None = None
    involvement: float | None = None
    is_root: bool


class DashboardGraphEdge(BaseModel):
    link_id: int
    src_post_id: int
    dst_post_id: int
    link_type: str
    direction: str
    score: float | None = None
    status: str


class EventGraphResponse(BaseModel):
    event: EventGraphEvent
    nodes: list[EventGraphNode]
    edges: list[DashboardGraphEdge]


class ProcessGraphSummary(BaseModel):
    process_id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    report_status: str
    events_count: int
    posts_count: int
    comments_count: int
    involvement: float | None = None


class ProcessGraphEvent(BaseModel):
    event_id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    relation_type: str
    direction: str
    score: float | None = None
    post_ids: list[int] = Field(default_factory=list)


class ProcessGraphMapping(BaseModel):
    process_id: int
    event_to_post_ids: dict[int, list[int]] = Field(default_factory=dict)

    model_config = ConfigDict(coerce_numbers_to_str=False)


class ProcessGraphResponse(BaseModel):
    summary: ProcessGraphSummary
    events: list[ProcessGraphEvent]
    nodes: list[EventGraphNode]
    edges: list[DashboardGraphEdge]
    mapping: ProcessGraphMapping
