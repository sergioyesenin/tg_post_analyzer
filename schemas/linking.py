from datetime import datetime

from pydantic import BaseModel


class LinkOut(BaseModel):
    id: int
    src_post_id: int
    dst_post_id: int
    link_type: str
    confidence: float | None = None
    evidence: dict | None = None
    model_version: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PostLinksResponse(BaseModel):
    post_id: int
    links: list[LinkOut]


class LinkRunResponse(BaseModel):
    post_id: int
    links_created: int
    event_id: int | None = None
    candidates_checked: int
    ai_checked: int = 0
    ai_links_created: int = 0
    ai_errors: int = 0


class EventSummaryOut(BaseModel):
    id: int
    title: str | None = None
    status: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    confidence: float | None = None
    summary_current: str | None = None

    class Config:
        from_attributes = True


class EventDetailOut(BaseModel):
    event: EventSummaryOut
    post_ids: list[int]


class RelatedPostOut(BaseModel):
    post_id: int
    channel_id: int
    channel_username: str
    date: datetime
    text_preview: str | None = None
    link_type: str
    link_type_ru: str
    confidence: float | None = None
    direction_ru: str


class GraphNodeOut(BaseModel):
    id: int
    label: str
    subtitle: str | None = None
    is_root: bool = False


class GraphEdgeOut(BaseModel):
    source: int
    target: int
    relation: str
    relation_ru: str
    confidence: float | None = None


class RelatedGraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class RelatedPostsResponse(BaseModel):
    root_post_id: int
    related_posts: list[RelatedPostOut]
    graph: RelatedGraphOut
