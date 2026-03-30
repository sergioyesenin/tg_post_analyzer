from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SentimentDistribution(BaseModel):
    positive: float = 0.0
    negative: float = 0.0
    neutral: float = 0.0


class SentimentSummary(BaseModel):
    dominant: str = "neutral"
    distribution: SentimentDistribution = Field(default_factory=SentimentDistribution)
    confidence: str | None = None


class ConfidenceSummary(BaseModel):
    overall: str = "medium"
    reason: str | None = None


class TopicSummary(BaseModel):
    name: str
    share: float | None = None


class ClusterSummary(BaseModel):
    cluster_id: str | None = None
    name: str
    size: int | None = None
    dominant_sentiment: str | None = None
    summary: str | None = None


class TrendSummary(BaseModel):
    period: str | None = None
    activity: str | None = None
    sentiment_shift: str | None = None
    summary: str


class PostReportPayload(BaseModel):
    type: str = "post_report_v2"
    status: str = "ready"
    post_id: int
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
