from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


class LinkOut(BaseModel):
    id: int
    src_post_id: int
    dst_post_id: int
    link_type: str
    direction: str
    score: float | None = None
    status: str
    evidence_json: dict | None = None
    model_version: str | None = None
    pipeline_version: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostLinksResponse(BaseModel):
    post_id: int
    links: list[LinkOut]


class LinkRunResponse(BaseModel):
    post_id: int
    links_verified: int
    links_proposed: int
    links_rejected: int
    candidates_checked: int
    verify_checked: int
    critic_checked: int
    queued_for_review: int = 0


class JobAcceptedResponse(BaseModel):
    status: str
    job_id: int
    job_type: str
    status_url: str
    result_url: str


class EventSummaryOut(BaseModel):
    id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    created_by: str | None = None
    comments_count: int = 0
    involvement: float | None = None

    model_config = ConfigDict(from_attributes=True)


class LinkedReportOut(BaseModel):
    id: int
    status: str
    version: int | None = None
    report_text: str | None = None
    report_json: dict | None = None
    created_at: datetime


class EventDetailOut(BaseModel):
    event: EventSummaryOut
    post_ids: list[int]
    root_post_id: int | None = None
    channels: list[str] = Field(default_factory=list)
    latest_report: LinkedReportOut | None = None


class ProcessSummaryOut(BaseModel):
    id: int
    title: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    created_by: str | None = None
    comments_count: int = 0
    involvement: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ProcessEventOut(BaseModel):
    event_id: int
    title: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    confidence: float | None = None
    relation_type: str
    direction: str
    score: float | None = None
    status: str
    post_ids: list[int] = Field(default_factory=list)


class ProcessDetailOut(BaseModel):
    process: ProcessSummaryOut
    events: list[ProcessEventOut]
    latest_report: LinkedReportOut | None = None


class AnchorPayload(BaseModel):
    shared_entities: list[str] = Field(default_factory=list)
    shared_places: list[str] = Field(default_factory=list)
    shared_dates: list[str] = Field(default_factory=list)
    shared_numbers: list[str] = Field(default_factory=list)
    shared_tickers: list[str] = Field(default_factory=list)


class EvidenceSpan(BaseModel):
    post: Literal["src", "dst"]
    quote: str = Field(min_length=1, max_length=500)


class VerifyFlags(BaseModel):
    time_consistent: bool
    entity_consistent: bool
    explicit_causality_marker: bool


class PairwiseVerifyResult(BaseModel):
    linked: Literal["true", "false", "unsure"]
    link_type: Literal[
        "same_event",
        "update",
        "contradiction",
        "cause",
        "consequence",
        "background",
        "related",
        "unrelated",
    ]
    direction: Literal["src_to_dst", "dst_to_src", "none"]
    anchors: AnchorPayload
    spans: list[EvidenceSpan] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=500)
    counterarguments: list[str] = Field(default_factory=list, min_length=2, max_length=3)
    flags: VerifyFlags

    @model_validator(mode="after")
    def ensure_spans_for_positive_links(self) -> "PairwiseVerifyResult":
        if self.linked == "false":
            return self
        posts = {span.post for span in self.spans}
        if "src" not in posts or "dst" not in posts:
            raise ValueError("spans must contain quotes for both src and dst posts when linked != false")
        return self


class CriticResult(BaseModel):
    verdict: Literal["approve", "reject", "needs_review"]
    issues: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    suggested_link_type: Literal[
        "same_event",
        "update",
        "contradiction",
        "cause",
        "consequence",
        "background",
        "related",
        "unrelated",
    ]
    notes: str = Field(default="", max_length=500)
