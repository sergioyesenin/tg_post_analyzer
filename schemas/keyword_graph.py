from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KeywordSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    date_from: datetime | None = None
    date_to: datetime | None = None
    channel_ids: list[int] = Field(default_factory=list)


class KeywordSearchItem(BaseModel):
    post_id: int
    channel_id: int
    channel_username: str | None = None
    date: datetime
    text_preview: str | None = None
    comments_count: int
    views: int | None = None
    involvement: float | None = None
    rank: float
    matched_lemmas: list[str] = Field(default_factory=list)


class KeywordSearchResponse(BaseModel):
    query: str
    normalized_query: str
    lemmas: list[str] = Field(default_factory=list)
    took_ms: int
    total: int
    items: list[KeywordSearchItem]


class GraphBuildRequest(BaseModel):
    post_ids: list[int] = Field(min_length=1, max_length=400)
    exclude_post_ids: list[int] = Field(default_factory=list)
    graph_mode: Literal["transient", "persisted"] = "transient"
    include_neighbors: bool = Field(default=True)
    neighbor_depth: int = Field(default=1, ge=0, le=3)
    neighbor_limit: int = Field(default=400, ge=1, le=2000)
    allowed_link_types: list[str] = Field(default_factory=list)
    min_shared_lemmas: int = Field(default=2, ge=1, le=20)
    max_time_distance_hours: int = Field(default=96, ge=1, le=24 * 30)
    min_text_similarity: float = Field(default=0.2, ge=0.0, le=1.0)


class GraphNodeOut(BaseModel):
    post_id: int
    channel_id: int
    channel_username: str | None = None
    date: datetime
    text_preview: str | None = None
    comments_count: int
    views: int | None = None
    involvement: float | None = None
    included_by: str = "seed"


class GraphEdgeOut(BaseModel):
    link_id: int
    src_post_id: int
    dst_post_id: int
    link_type: str
    direction: str
    score: float | None = None
    status: str
    edge_source: str = "persisted"
    evidence: dict | None = None


class GraphBuildResponse(BaseModel):
    seed_post_ids: list[int]
    excluded_post_ids: list[int]
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class GraphReportRequest(BaseModel):
    title: str | None = None
    post_ids: list[int] = Field(min_length=1, max_length=300)
    exclude_post_ids: list[int] = Field(default_factory=list)
    graph_mode: Literal["transient", "persisted"] = "transient"
    include_neighbors: bool = Field(default=True)
    neighbor_depth: int = Field(default=1, ge=0, le=3)
    neighbor_limit: int = Field(default=400, ge=1, le=2000)
    allowed_link_types: list[str] = Field(default_factory=list)
    min_shared_lemmas: int = Field(default=2, ge=1, le=20)
    max_time_distance_hours: int = Field(default=96, ge=1, le=24 * 30)
    min_text_similarity: float = Field(default=0.2, ge=0.0, le=1.0)


class GraphReportResponse(BaseModel):
    status: str
    title: str
    post_ids: list[int]
    excluded_post_ids: list[int]
    content: str
