from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SentimentDistribution(BaseModel):
    positive: float = Field(default=0.0, ge=0.0, le=1.0)
    negative: float = Field(default=0.0, ge=0.0, le=1.0)
    neutral: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class SentimentSummary(BaseModel):
    dominant: Literal["positive", "negative", "neutral"] = "neutral"
    distribution: SentimentDistribution = Field(default_factory=SentimentDistribution)
    confidence: Literal["low", "medium", "high"] | None = None

    model_config = ConfigDict(extra="forbid")


class ConfidenceSummary(BaseModel):
    overall: Literal["low", "medium", "high"] = "medium"
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class TopicSummary(BaseModel):
    name: str
    share: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ClusterSummary(BaseModel):
    cluster_id: str | None = None
    name: str
    size: int | None = None
    dominant_sentiment: Literal["positive", "negative", "neutral"] | None = None
    summary: str | None = None

    model_config = ConfigDict(extra="forbid")


class TrendSummary(BaseModel):
    period: str | None = None
    activity: Literal["low", "medium", "high"] | None = None
    sentiment_shift: Literal["positive", "negative", "neutral", "mixed", "stable"] | None = None
    summary: str

    model_config = ConfigDict(extra="forbid")


class PostReportPayload(BaseModel):
    type: Literal["post_report_v2"] = "post_report_v2"
    status: Literal["ready", "skipped_min_comments", "failed"] = "ready"
    post_id: int
    published_at: str | None = None
    title: str
    summary: str
    comment_count: int = 0
    sentiment: SentimentSummary = Field(default_factory=SentimentSummary)
    topics: list[TopicSummary] = Field(default_factory=list)
    clusters: list[ClusterSummary] = Field(default_factory=list)
    time_trends: list[TrendSummary] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    representative_quotes: list[str] = Field(default_factory=list)
    confidence: ConfidenceSummary = Field(default_factory=ConfidenceSummary)
    meta: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class EventReportPayload(BaseModel):
    type: str = "event_report_v2"
    status: str = "ready"
    event_id: int
    event_title: str
    posts_count: int = 0
    source_post_reports: list[int] = Field(default_factory=list)
    sentiment: SentimentSummary = Field(default_factory=SentimentSummary)
    cross_post_topics: list[TopicSummary] = Field(default_factory=list)
    post_dynamics: list[dict] = Field(default_factory=list)
    event_trends: list[dict] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    summary: str
    confidence: ConfidenceSummary = Field(default_factory=ConfidenceSummary)
    meta: dict = Field(default_factory=dict)


class ProcessReportPayload(BaseModel):
    type: str = "process_report_v2"
    status: str = "ready"
    process_id: int
    process_title: str
    events_count: int = 0
    source_event_reports: list[int] = Field(default_factory=list)
    overall_sentiment: SentimentSummary = Field(default_factory=SentimentSummary)
    stage_analysis: list[dict] = Field(default_factory=list)
    process_trends: list[dict] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    summary: str
    confidence: ConfidenceSummary = Field(default_factory=ConfidenceSummary)
    meta: dict = Field(default_factory=dict)


class ReportOut(BaseModel):
    id: int
    post_id: int
    status: str
    content: str | None = None
    report_json: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
