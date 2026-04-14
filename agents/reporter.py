from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

import litellm
from litellm import acompletion
from pydantic import ValidationError

from config import settings
from schemas.report import PostReportPayload

try:
    from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter

    _NATASHA_AVAILABLE = True
except Exception:
    _NATASHA_AVAILABLE = False

try:
    from transformers import pipeline as hf_pipeline

    _TRANSFORMERS_AVAILABLE = True
except Exception:
    _TRANSFORMERS_AVAILABLE = False


def _disable_litellm_cold_storage_logging() -> None:
    try:
        from litellm.litellm_core_utils.litellm_logging import StandardLoggingPayloadSetup
    except Exception:
        return

    if getattr(StandardLoggingPayloadSetup, "_tg_post_analyzer_cold_storage_disabled", False):
        return

    def _no_cold_storage(*_args: Any, **_kwargs: Any) -> None:
        return None

    StandardLoggingPayloadSetup._generate_cold_storage_object_key = staticmethod(_no_cold_storage)
    StandardLoggingPayloadSetup._tg_post_analyzer_cold_storage_disabled = True


@dataclass(frozen=True)
class ReportConfig:
    min_comments: int = 20
    report_word_target: int = 350
    report_word_min: int = 200
    report_word_max: int = 500


@dataclass(frozen=True)
class ReportLLMSettings:
    llm_model: str = "ollama/llama3:8b-instruct-q4_K_M"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str | None = None


@dataclass(frozen=True)
class EpistemicEntry:
    label: str  # One of EPISTEMIC_LABELS
    evidence: str
    confidence: str  # "high", "medium", "low"


@dataclass(frozen=True)
class MultiAgentMeta:
    """Internal meta schema for multi-agent analysis traces."""
    epistemic_labels: list[EpistemicEntry] = field(default_factory=list)
    sufficiency: str = "insufficient"  # One of SUFFICIENCY_LABELS
    stages: dict[str, Any] = field(default_factory=dict)  # For future stage outputs
    review_iterations: int = 0
    final_status: str = "insufficient_data"  # One of REPORT_STATUSES or FALLBACK_STATUSES


def load_report_llm_settings() -> ReportLLMSettings:
    return ReportLLMSettings(
        llm_model=settings.REPORT_LLM_MODEL,
        llm_base_url=settings.REPORT_LLM_BASE_URL,
        llm_api_key=settings.REPORT_LLM_API_KEY,
    )


TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]{3,}")
URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
STOPWORDS_RU = {
    "это", "что", "как", "для", "все", "или", "его", "ее", "про", "под", "при", "без", "над", "ещё", "еще",
    "они", "она", "оно", "мы", "вы", "ты", "так", "там", "тут", "где", "когда", "пока", "потом", "если",
    "ли", "же", "бы", "был", "была", "были", "будет", "будут", "есть", "нет", "да", "уже", "только", "очень",
    "просто", "после", "перед", "между", "этого", "этой", "этот", "эти", "того", "того", "который", "которая",
    "которые", "their", "this", "that", "with", "from", "have", "will", "about", "they", "them", "just",
}
POSITIVE_MARKERS = {
    "хорошо", "отлично", "супер", "класс", "спасибо", "поддерживаю", "верно", "согласен", "норм", "ok", "good",
}
NEGATIVE_MARKERS = {
    "плохо", "ужас", "позор", "бред", "ложь", "вранье", "кошмар", "стыд", "проблема", "fake", "bad",
}


POS_EXCLUDE = {"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "SCONJ"}
ENTITY_LABEL_MAP = {"PER": "persons", "ORG": "organizations", "LOC": "locations"}
_segmenter = None
_morph_vocab = None
_morph_tagger = None
_ner_tagger = None
_natasha_init_failed = False
_sentiment_pipeline = None
_sentiment_init_failed = False
POST_REPORT_PROMPT_MAX_POST_CHARS = 2200
POST_REPORT_PROMPT_MAX_MEDIA_LINKS = 5
POST_REPORT_PROMPT_MAX_KEYWORDS = 6
POST_REPORT_PROMPT_MAX_SAMPLES = 6
POST_REPORT_PROMPT_MAX_QUOTES = 5
POST_REPORT_PROMPT_MAX_ENTITY_VALUES = 5
POST_REPORT_MAX_RETRIES = 2
POST_REPORT_TIMEOUT_SECONDS = 120
POST_REPORT_MAX_TOKENS = 1000
POST_REPORT_TIMEOUT_MIN_SECONDS = 15
POST_REPORT_TIMEOUT_RESERVED_SECONDS = 10
POST_REPORT_STAGE_SEQUENCE = ("context", "routing", "expert", "public_opinion", "synthesis")
POST_REPORT_REVIEWER_STAGE = "reviewer"

# Spec-derived constants for multi-agent analysis vocabulary
EPISTEMIC_LABELS = frozenset(["fact", "derived", "interpretation", "external", "uncertain"])
SUFFICIENCY_LABELS = frozenset(["sufficient", "limited", "weak_signal", "insufficient"])
REPORT_STATUSES = frozenset(["ready", "limited", "insufficient_data"])
REVIEW_BUDGET_MAX_ITERATIONS = 2
FALLBACK_STATUSES = frozenset(["ready", "limited", "insufficient_data", "failed"])
REVIEW_DECISIONS = frozenset(["accept", "rerun", "downgrade"])


def _safe_text(value: str | None, *, limit: int = 500) -> str:
    return " ".join((value or "").strip().split())[:limit]


def _get_natasha_components():
    global _segmenter, _morph_vocab, _morph_tagger, _ner_tagger, _natasha_init_failed
    if not _NATASHA_AVAILABLE or _natasha_init_failed:
        return None
    if _segmenter is not None:
        return _segmenter, _morph_vocab, _morph_tagger, _ner_tagger
    try:
        emb = NewsEmbedding()
        _segmenter = Segmenter()
        _morph_vocab = MorphVocab()
        _morph_tagger = NewsMorphTagger(emb)
        _ner_tagger = NewsNERTagger(emb)
    except Exception:
        _natasha_init_failed = True
        return None
    return _segmenter, _morph_vocab, _morph_tagger, _ner_tagger


def _normalize_entity_value(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip(" \t\r\n.,:;!?\"'`[](){}<>«»"))


def _analyze_text(text: str) -> dict[str, Any]:
    cleaned = _safe_text(text, limit=1200)
    if not cleaned:
        return {"tokens": [], "entities": {"persons": [], "organizations": [], "locations": []}}

    components = _get_natasha_components()
    if components is None:
        tokens = [{"text": raw, "lemma": raw, "pos": None} for raw in TOKEN_RE.findall(cleaned.lower())]
        return {"tokens": tokens, "entities": {"persons": [], "organizations": [], "locations": []}}

    segmenter, morph_vocab, morph_tagger, ner_tagger = components
    doc = Doc(cleaned)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    doc.tag_ner(ner_tagger)

    tokens: list[dict[str, Any]] = []
    for token in doc.tokens:
        text_value = (token.text or "").lower().strip()
        if not text_value or not TOKEN_RE.fullmatch(text_value):
            continue
        try:
            token.lemmatize(morph_vocab)
            lemma = (token.lemma or text_value).lower().strip()
        except Exception:
            lemma = text_value
        tokens.append({"text": text_value, "lemma": lemma, "pos": getattr(token, "pos", None)})

    entities: dict[str, list[str]] = {"persons": [], "organizations": [], "locations": []}
    seen_entities: dict[str, set[str]] = {key: set() for key in entities}
    for span in getattr(doc, "spans", []) or []:
        bucket = ENTITY_LABEL_MAP.get(getattr(span, "type", ""))
        if not bucket:
            continue
        try:
            span.normalize(morph_vocab)
            value = _normalize_entity_value(getattr(span, "normal", None) or getattr(span, "text", ""))
        except Exception:
            value = _normalize_entity_value(getattr(span, "text", ""))
        if not value or value in seen_entities[bucket]:
            continue
        seen_entities[bucket].add(value)
        entities[bucket].append(value)
    return {"tokens": tokens, "entities": entities}


def _get_sentiment_pipeline():
    global _sentiment_pipeline, _sentiment_init_failed
    if _sentiment_pipeline is not None:
        return _sentiment_pipeline
    if _sentiment_init_failed or not _TRANSFORMERS_AVAILABLE:
        return None
    model_name = (os.getenv("POST_REPORT_SENTIMENT_MODEL") or "").strip()
    if not model_name:
        _sentiment_init_failed = True
        return None
    try:
        _sentiment_pipeline = hf_pipeline("text-classification", model=model_name, tokenizer=model_name)
    except Exception:
        _sentiment_init_failed = True
        return None
    return _sentiment_pipeline


def _configured_sentiment_model_name() -> str | None:
    model_name = (os.getenv("POST_REPORT_SENTIMENT_MODEL") or "").strip()
    return model_name or None


def _build_sentiment_diagnostics(sentiment_hint: dict[str, Any] | None = None) -> dict[str, Any]:
    hint = dict(sentiment_hint or {})
    backend = str(hint.get("backend") or "fallback_neutral").strip() or "fallback_neutral"
    model_name = _configured_sentiment_model_name()
    diagnostics: dict[str, Any] = {
        "backend": backend,
        "model": model_name,
        "configured": bool(model_name),
        "transformers_available": bool(_TRANSFORMERS_AVAILABLE),
    }
    if backend == "fallback_neutral":
        if not _TRANSFORMERS_AVAILABLE:
            diagnostics["fallback_reason"] = "transformers_unavailable"
        elif not model_name:
            diagnostics["fallback_reason"] = "model_not_configured"
        elif _sentiment_init_failed:
            diagnostics["fallback_reason"] = "pipeline_init_failed"
        else:
            diagnostics["fallback_reason"] = "runtime_fallback"
    if hint:
        diagnostics["hint"] = {
            "dominant": str(hint.get("dominant_hint") or "neutral"),
            "distribution": dict(hint.get("distribution_hint") or {}),
            "confidence": str(hint.get("confidence") or "low"),
        }
    return diagnostics


def _normalize_sentiment_label(label: Any) -> str:
    normalized = str(label or "").strip().lower()
    if any(marker in normalized for marker in ("pos", "label_2", "4 stars", "5 stars")):
        return "positive"
    if any(marker in normalized for marker in ("neg", "label_0", "1 star", "2 stars")):
        return "negative"
    return "neutral"


def _normalize_comment_text(text: str) -> str:
    return _safe_text(text, limit=500)


def _bucket_share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _build_comment_records(comments: list[str], thread_comments: list[dict] | None = None) -> list[dict]:
    records: list[dict] = []
    if thread_comments:
        for idx, raw in enumerate(thread_comments, start=1):
            text = _normalize_comment_text(str(raw.get("text") or ""))
            if not text:
                continue
            records.append(
                {
                    "id": int(raw.get("id") or idx),
                    "parent_id": raw.get("parent_id"),
                    "depth": int(raw.get("depth") or 0),
                    "date": raw.get("date"),
                    "text": text,
                    "analysis": _analyze_text(text),
                }
            )
        if records:
            return records

    for idx, text in enumerate(comments, start=1):
        normalized = _normalize_comment_text(text)
        if not normalized:
            continue
        records.append(
            {
                "id": idx,
                "parent_id": None,
                "depth": 0,
                "date": None,
                "text": normalized,
                "analysis": _analyze_text(normalized),
            }
        )
    return records


def _extract_keywords(records: list[dict], *, limit: int = 8) -> list[dict]:
    counts: dict[str, int] = {}
    for record in records:
        seen_local: set[str] = set()
        for token_meta in record.get("analysis", {}).get("tokens", []):
            token = str(token_meta.get("lemma") or token_meta.get("text") or "").lower()
            if len(token) < 3 or token.isdigit():
                continue
            if token_meta.get("pos") in POS_EXCLUDE:
                continue
            if token in seen_local:
                continue
            counts[token] = counts.get(token, 0) + 1
            seen_local.add(token)
    total = max(1, len(records))
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"term": token, "share": _bucket_share(count, total), "count": count} for token, count in ordered[:limit]]


def _extract_named_entities(records: list[dict], *, limit: int = 10) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"persons": [], "organizations": [], "locations": []}
    seen: dict[str, set[str]] = {key: set() for key in buckets}
    for record in records:
        entities = record.get("analysis", {}).get("entities", {})
        for bucket in buckets:
            for value in entities.get(bucket, []):
                normalized = _normalize_entity_value(value)
                if not normalized or normalized in seen[bucket]:
                    continue
                seen[bucket].add(normalized)
                buckets[bucket].append(normalized)
    return {bucket: values[:limit] for bucket, values in buckets.items()}


def _sentiment_signal_summary(records: list[dict]) -> dict:
    classifier = _get_sentiment_pipeline()
    if classifier is None:
        return {
            "dominant_hint": "neutral",
            "distribution_hint": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "low",
            "backend": "fallback_neutral",
        }

    samples = [record["text"][:320] for record in records[:24] if record.get("text")]
    try:
        responses = classifier(samples, truncation=True, max_length=512) if samples else []
    except Exception:
        responses = []
    positive = 0
    negative = 0
    neutral = 0
    for response in responses:
        label = _normalize_sentiment_label(response.get("label"))
        if label == "positive":
            positive += 1
        elif label == "negative":
            negative += 1
        else:
            neutral += 1
    total = max(1, len(responses))
    dominant = "neutral"
    if positive > negative and positive > neutral:
        dominant = "positive"
    elif negative > positive and negative > neutral:
        dominant = "negative"
    return {
        "dominant_hint": dominant,
        "distribution_hint": {
            "positive": _bucket_share(positive, total),
            "negative": _bucket_share(negative, total),
            "neutral": _bucket_share(neutral, total),
        },
        "confidence": "medium" if responses else "low",
        "backend": "transformers",
    }


def _article_sufficiency_label(post_text: str, named_entities: dict[str, list[str]], top_keywords: list[dict]) -> str:
    stripped = (post_text or "").strip()
    if not stripped:
        return "insufficient"

    length = len(stripped)
    keyword_count = len(top_keywords)
    entity_count = sum(len(values) for values in named_entities.values())

    if length < 60:
        return "weak_signal"
    if length < 140:
        return "limited" if keyword_count < 2 and entity_count < 2 else "weak_signal"
    if keyword_count < 2 and entity_count < 2:
        return "limited"
    return "sufficient"


def _comment_sufficiency_label(records: list[dict], sentiment_hint: dict[str, Any], top_keywords: list[dict]) -> str:
    total = len(records)
    if total == 0:
        return "insufficient"
    if total < 5:
        return "weak_signal"

    distribution = sentiment_hint.get("distribution_hint") or {}
    positive = float(distribution.get("positive") or 0.0)
    negative = float(distribution.get("negative") or 0.0)
    neutral = float(distribution.get("neutral") or 0.0)
    active_share = positive + negative
    keyword_count = len(top_keywords)

    if total < 10:
        if neutral > 0.75 or active_share < 0.15:
            return "weak_signal"
        return "limited"

    if neutral > 0.8:
        return "weak_signal"
    if active_share < 0.2:
        return "limited"
    if keyword_count < 2:
        return "limited"
    if positive > 0.65 or negative > 0.65:
        return "sufficient"
    return "limited"


def _overall_sufficiency_label(article_label: str, comment_label: str) -> str:
    if article_label == "insufficient" or comment_label == "insufficient":
        return "insufficient"
    if article_label == "weak_signal" or comment_label == "weak_signal":
        return "weak_signal"
    if article_label == "limited" or comment_label == "limited":
        return "limited"
    return "sufficient"


def _discussion_state(records: list[dict], sentiment_hint: dict[str, Any], thread_shape: dict[str, Any], engagement_markers: dict[str, Any]) -> str:
    total = len(records)
    if total < 4:
        return "sparse"

    distribution = sentiment_hint.get("distribution_hint") or {}
    positive = float(distribution.get("positive") or 0.0)
    negative = float(distribution.get("negative") or 0.0)
    neutral = float(distribution.get("neutral") or 0.0)

    if positive > 0.25 and negative > 0.25:
        return "conflicted"
    if engagement_markers.get("links_share", 0.0) > 0.20 or engagement_markers.get("exclamations_share", 0.0) > 0.15:
        return "noisy"
    if thread_shape.get("replies_deeper", 0) > 0 and thread_shape.get("replies_level_1", 0) / max(1, thread_shape.get("root_comments", 1)) > 1.5:
        return "conflicted"
    if neutral > 0.8:
        return "stable"
    return "uncertain"


def _build_evidence_candidates(records: list[dict], top_keywords: list[dict], *, limit: int = 5) -> list[dict]:
    candidates: list[dict] = []
    keyword_terms = [item["term"] for item in top_keywords if isinstance(item, dict) and isinstance(item.get("term"), str)]
    for record in records:
        text = record.get("text", "")
        lowered = text.lower()
        evidence_terms = [term for term in keyword_terms if term in lowered]
        score = 0
        if URL_RE.search(lowered):
            score += 2
        if "?" in text or "!" in text:
            score += 1
        if any(marker in lowered for marker in POSITIVE_MARKERS | NEGATIVE_MARKERS):
            score += 1
        score += len(evidence_terms)
        if score <= 0:
            continue
        candidates.append(
            {
                "id": int(record.get("id") or 0),
                "text": text if len(text) <= 220 else text[:217] + "...",
                "evidence_terms": evidence_terms,
                "sentiment_hints": {
                    "contains_positive": any(marker in lowered for marker in POSITIVE_MARKERS),
                    "contains_negative": any(marker in lowered for marker in NEGATIVE_MARKERS),
                    "has_link": bool(URL_RE.search(lowered)),
                    "has_question": "?" in text,
                    "has_exclamation": "!" in text,
                },
                "score": score,
            }
        )

    if not candidates:
        for record in records[:limit]:
            text = record.get("text", "")
            candidates.append(
                {
                    "id": int(record.get("id") or 0),
                    "text": text if len(text) <= 220 else text[:217] + "...",
                    "evidence_terms": [],
                    "sentiment_hints": {
                        "contains_positive": any(marker in text.lower() for marker in POSITIVE_MARKERS),
                        "contains_negative": any(marker in text.lower() for marker in NEGATIVE_MARKERS),
                        "has_link": bool(URL_RE.search(text)),
                        "has_question": "?" in text,
                        "has_exclamation": "!" in text,
                    },
                    "score": 0,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["id"]))
    return candidates[:limit]


def _evaluate_retrieval_policy(signal_summary: dict[str, Any], post_text: str) -> dict[str, Any]:
    policy_enabled = bool(getattr(settings, "RETRIEVAL_POLICY_ENABLED", False))
    provider_enabled = bool(getattr(settings, "RETRIEVAL_PROVIDER_ENABLED", False))
    provider_name = str(getattr(settings, "RETRIEVAL_PROVIDER_NAME", "none") or "none")

    if not policy_enabled:
        return {
            "policy_enabled": False,
            "provider_enabled": provider_enabled,
            "provider_name": provider_name,
            "provider_available": provider_enabled,
            "required": False,
            "used": False,
            "status": "disabled",
            "reason": "retrieval_policy_disabled",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    discussion_state = str(signal_summary.get("discussion_state") or "")
    sufficiency = str(signal_summary.get("sufficiency") or "")
    article_sufficiency = str(signal_summary.get("article_sufficiency") or "")
    required = discussion_state in {"conflicted", "noisy"} or sufficiency in {"insufficient", "weak_signal"} or article_sufficiency == "insufficient"
    if discussion_state in {"conflicted", "noisy"}:
        reason = "conflicted_discussion"
    elif article_sufficiency == "insufficient":
        reason = "missing_post_content"
    elif sufficiency in {"insufficient", "weak_signal"}:
        reason = "low_internal_sufficiency"
    else:
        reason = "sufficient_internal_signal"

    if required and not provider_enabled:
        status = "required_but_unavailable"
    elif required:
        status = "required"
    else:
        status = "not_required"

    return {
        "policy_enabled": True,
        "provider_enabled": provider_enabled,
        "provider_name": provider_name,
        "provider_available": provider_enabled,
        "required": required,
        "used": False,
        "status": status,
        "reason": reason,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _representative_samples(records: list[dict], *, limit: int = 8) -> list[dict]:
    ranked = sorted(
        records,
        key=lambda item: (
            -min(int(item.get("depth") or 0), 3),
            -sum(len(values) for values in item.get("analysis", {}).get("entities", {}).values()),
            -len(item.get("analysis", {}).get("tokens", [])),
            -len(item["text"]),
            item.get("date") or "",
            int(item.get("id") or 0),
        ),
    )
    samples: list[dict] = []
    seen_texts: set[str] = set()
    for record in ranked:
        text = record["text"]
        if text in seen_texts:
            continue
        seen_texts.add(text)
        samples.append(
            {
                "id": int(record.get("id") or 0),
                "depth": int(record.get("depth") or 0),
                "date": record.get("date"),
                "text": text[:240],
            }
        )
        if len(samples) >= limit:
            break
    return samples


def build_post_signal_summary(
    *,
    post_text: str,
    comments: list[str],
    thread_comments: Optional[list[dict]] = None,
    views: Optional[int] = None,
) -> dict[str, Any]:
    records = _build_comment_records(comments, thread_comments)
    total = len(records)
    depth_counts: dict[str, int] = {"root": 0, "reply": 0, "deep_reply": 0}
    question_count = 0
    exclaim_count = 0
    url_count = 0
    for record in records:
        depth = int(record.get("depth") or 0)
        if depth <= 0:
            depth_counts["root"] += 1
        elif depth == 1:
            depth_counts["reply"] += 1
        else:
            depth_counts["deep_reply"] += 1
        text = record["text"]
        if "?" in text:
            question_count += 1
        if "!" in text:
            exclaim_count += 1
        if URL_RE.search(text):
            url_count += 1

    avg_length = round(sum(len(record["text"]) for record in records) / total, 1) if total else 0.0
    top_keywords = _extract_keywords(records)
    named_entities = _extract_named_entities(records)
    sentiment_hint = _sentiment_signal_summary(records)
    samples = _representative_samples(records)
    post_analysis = _analyze_text(post_text or "")
    post_tokens = {
        str(token_meta.get("lemma") or token_meta.get("text") or "").lower()
        for token_meta in post_analysis.get("tokens", [])
        if len(str(token_meta.get("lemma") or token_meta.get("text") or "")) >= 3
        and token_meta.get("pos") not in POS_EXCLUDE
    }
    keyword_terms = [item["term"] for item in top_keywords]
    overlap = [term for term in keyword_terms if term in post_tokens]
    sentiment_diagnostics = _build_sentiment_diagnostics(sentiment_hint)
    article_sufficiency = _article_sufficiency_label(post_text or "", named_entities, top_keywords)
    comment_sufficiency = _comment_sufficiency_label(records, sentiment_hint, top_keywords)
    sufficiency = _overall_sufficiency_label(article_sufficiency, comment_sufficiency)
    discussion_state_label = _discussion_state(
        records,
        sentiment_hint,
        {
            "root_comments": depth_counts["root"],
            "replies_level_1": depth_counts["reply"],
            "replies_deeper": depth_counts["deep_reply"],
        },
        {
            "questions_share": _bucket_share(question_count, total),
            "exclamations_share": _bucket_share(exclaim_count, total),
            "links_share": _bucket_share(url_count, total),
        },
    )
    evidence_candidates = _build_evidence_candidates(records, top_keywords)

    return {
        "comment_count": total,
        "views": views,
        "post_length_chars": len((post_text or "").strip()),
        "average_comment_length_chars": avg_length,
        "thread_shape": {
            "root_comments": depth_counts["root"],
            "replies_level_1": depth_counts["reply"],
            "replies_deeper": depth_counts["deep_reply"],
        },
        "engagement_markers": {
            "questions_share": _bucket_share(question_count, total),
            "exclamations_share": _bucket_share(exclaim_count, total),
            "links_share": _bucket_share(url_count, total),
        },
        "sentiment_hint": sentiment_hint,
        "top_keywords": top_keywords,
        "named_entities": named_entities,
        "post_keyword_overlap": overlap[:5],
        "representative_samples": samples,
        "article_sufficiency": article_sufficiency,
        "comment_sufficiency": comment_sufficiency,
        "sufficiency": sufficiency,
        "discussion_state": discussion_state_label,
        "weak_signal": comment_sufficiency == "weak_signal",
        "public_opinion_strength": "weak" if comment_sufficiency == "weak_signal" else "medium" if comment_sufficiency == "limited" else "strong",
        "evidence_candidates": evidence_candidates,
        "nlp_backend": {
            "lemmatizer": "natasha" if _get_natasha_components() is not None else "regex_fallback",
            "sentiment": sentiment_hint.get("backend", "fallback_neutral"),
            "sentiment_diagnostics": sentiment_diagnostics,
        },
    }


def _compact_signal_summary_for_prompt(signal_summary: dict[str, Any]) -> dict[str, Any]:
    named_entities = signal_summary.get("named_entities") or {}
    return {
        "comment_count": int(signal_summary.get("comment_count") or 0),
        "views": signal_summary.get("views"),
        "post_length_chars": int(signal_summary.get("post_length_chars") or 0),
        "average_comment_length_chars": signal_summary.get("average_comment_length_chars"),
        "thread_shape": dict(signal_summary.get("thread_shape") or {}),
        "engagement_markers": dict(signal_summary.get("engagement_markers") or {}),
        "sentiment_hint": dict(signal_summary.get("sentiment_hint") or {}),
        "top_keywords": list(signal_summary.get("top_keywords") or [])[:POST_REPORT_PROMPT_MAX_KEYWORDS],
        "named_entities": {
            "persons": list(named_entities.get("persons") or [])[:POST_REPORT_PROMPT_MAX_ENTITY_VALUES],
            "organizations": list(named_entities.get("organizations") or [])[:POST_REPORT_PROMPT_MAX_ENTITY_VALUES],
            "locations": list(named_entities.get("locations") or [])[:POST_REPORT_PROMPT_MAX_ENTITY_VALUES],
        },
        "post_keyword_overlap": list(signal_summary.get("post_keyword_overlap") or [])[:POST_REPORT_PROMPT_MAX_KEYWORDS],
        "representative_samples": list(signal_summary.get("representative_samples") or [])[:POST_REPORT_PROMPT_MAX_SAMPLES],
        "article_sufficiency": signal_summary.get("article_sufficiency"),
        "comment_sufficiency": signal_summary.get("comment_sufficiency"),
        "sufficiency": signal_summary.get("sufficiency"),
        "discussion_state": signal_summary.get("discussion_state"),
        "weak_signal": signal_summary.get("weak_signal"),
        "public_opinion_strength": signal_summary.get("public_opinion_strength"),
        "nlp_backend": dict(signal_summary.get("nlp_backend") or {}),
    }


def _build_post_report_prompt(
    *,
    channel: str,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    views: Optional[int],
    media_links: Optional[list[str]],
    signal_summary: dict[str, Any],
) -> str:
    compact_summary = _compact_signal_summary_for_prompt(signal_summary)
    return f"""
Return one valid JSON object only. No markdown. No prose outside JSON.
Language of all natural-language fields must be Russian.

Task: analyze one Telegram post using normalized comment signals and deterministic representative samples, then build a compact structured report based on five analytical components: Event (the post content), Context (background and metadata), Reaction (audience sentiment and engagement), Interpretation (thematic analysis and patterns), Consequences (implications and risks).
Use only these sentiment labels: positive, negative, neutral.
Do not invent facts. If confidence is low, say so in confidence.reason.
Treat representative_samples as evidence examples, and treat post_signal_summary as the primary source for counts, structure, topic hints and entities.
Pay special attention to post_signal_summary.article_sufficiency, post_signal_summary.comment_sufficiency, post_signal_summary.discussion_state, and post_signal_summary.weak_signal when judging how confidently to describe public opinion.
If the evidence is weak or partial, summarize conservatively.
The resulting payload must be sufficient to render a structured Russian mini-report with these sections:
- Event: core post content and immediate context,
- Context: channel background and publication details,
- Reaction: overall tone of discussion with percentage sentiment split,
- Interpretation: key topics, trends and recurring patterns, thematic classification,
- Consequences: representative quotes, risks/signals, and implications.
Prefer concise topic names, cluster summaries suitable for thematic classification, and time_trends that describe temporal dynamics or recurring patterns.
Assume short Russian-language comments are common; infer cautiously and avoid overclaiming.

Required JSON schema:
{{
  "type": "post_report_v2",
  "status": "ready",
  "title": "string",
  "summary": "string",
  "comment_count": {int(signal_summary.get("comment_count") or 0)},
  "sentiment": {{
    "dominant": "positive|negative|neutral",
    "distribution": {{
      "positive": 0.0,
      "negative": 0.0,
      "neutral": 0.0
    }},
    "confidence": "low|medium|high"
  }},
  "topics": [{{"name": "string", "share": 0.0}}],
  "clusters": [
    {{
      "cluster_id": "string",
      "name": "string",
      "size": 0,
      "dominant_sentiment": "positive|negative|neutral",
      "summary": "string"
    }}
  ],
  "time_trends": [
    {{
      "period": "string",
      "activity": "low|medium|high",
      "sentiment_shift": "positive|negative|neutral|mixed|stable",
      "summary": "string"
    }}
  ],
  "risks": ["string"],
  "anomalies": ["string"],
  "representative_quotes": ["string"],
  "confidence": {{
    "overall": "low|medium|high",
    "reason": "string"
  }},
  "meta": {{
    "prompt_version": "post_report_v2"
  }}
}}

Input:
- channel: {channel}
- post_id: {post_id}
- published_at: {published_at_iso}
- views: {"" if views is None else views}
- media_links: {", ".join((media_links or [])[:POST_REPORT_PROMPT_MAX_MEDIA_LINKS])}
- post_text:
{_short_text(post_text or "", max_chars_each=POST_REPORT_PROMPT_MAX_POST_CHARS)}

- post_signal_summary:
{_format_signal_summary(compact_summary)}
"""


def _normalize_distribution_sum(distribution: dict[str, Any]) -> dict[str, float]:
    positive = float(distribution.get("positive", 0.0) or 0.0)
    negative = float(distribution.get("negative", 0.0) or 0.0)
    neutral = float(distribution.get("neutral", 0.0) or 0.0)
    total = positive + negative + neutral
    if total <= 0:
        return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
    return {
        "positive": round(positive / total, 4),
        "negative": round(negative / total, 4),
        "neutral": round(neutral / total, 4),
    }


def _validate_post_report_payload(
    payload: dict[str, Any],
    *,
    post_id: int,
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any] | None = None,
    stage_traces: dict[str, Any] | None = None,
    orchestration_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["type"] = "post_report_v2"
    normalized["post_id"] = int(post_id)
    normalized["comment_count"] = int(signal_summary.get("comment_count") or 0)
    normalized.setdefault(
        "representative_quotes",
        [sample.get("text", "") for sample in list(signal_summary.get("representative_samples") or [])[:POST_REPORT_PROMPT_MAX_QUOTES]],
    )
    sentiment = dict(normalized.get("sentiment") or {})
    sentiment["distribution"] = _normalize_distribution_sum(dict(sentiment.get("distribution") or {}))
    normalized["sentiment"] = sentiment
    meta = dict(normalized.get("meta") or {})
    meta.setdefault("prompt_version", "post_report_v2")
    meta.setdefault("input_mode", "preprocessed_signals_v1")
    meta.setdefault(
        "input_summary",
        {
            "comment_count": int(signal_summary.get("comment_count") or 0),
            "top_keywords": [item["term"] for item in list(signal_summary.get("top_keywords") or [])[:5] if isinstance(item, dict) and item.get("term")],
            "sample_count": len(list(signal_summary.get("representative_samples") or [])),
            "article_sufficiency": signal_summary.get("article_sufficiency"),
            "comment_sufficiency": signal_summary.get("comment_sufficiency"),
            "sufficiency": signal_summary.get("sufficiency"),
            "discussion_state": signal_summary.get("discussion_state"),
            "weak_signal": signal_summary.get("weak_signal"),
        },
    )
    sentiment_diagnostics = dict(((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics")) or {})
    meta.setdefault("nlp_backend", dict(signal_summary.get("nlp_backend") or {}))
    meta.setdefault("sentiment_hint", dict(signal_summary.get("sentiment_hint") or {}))
    meta.setdefault("sentiment_backend", sentiment_diagnostics.get("backend") or "fallback_neutral")
    meta.setdefault("sentiment_model", sentiment_diagnostics.get("model"))
    meta.setdefault("sentiment_model_configured", bool(sentiment_diagnostics.get("configured")))
    meta.setdefault("sentiment_transformers_available", bool(sentiment_diagnostics.get("transformers_available")))
    if sentiment_diagnostics.get("fallback_reason"):
        meta.setdefault("sentiment_fallback_reason", sentiment_diagnostics.get("fallback_reason"))
    multi_agent = meta.setdefault("multi_agent", {
        "epistemic_labels": [],  # List of EpistemicEntry dicts
        "sufficiency": "insufficient",  # Will be updated based on data sufficiency
        "stages": {},  # For future stage outputs
        "review_iterations": 0,
        "final_status": "insufficient_data",
    })
    multi_agent["sufficiency"] = signal_summary.get("sufficiency") or multi_agent.get("sufficiency", "insufficient")
    stages = dict(multi_agent.get("stages") or {})
    if stage_traces is not None:
        stages.update(stage_traces)
    if retrieval_trace is not None:
        stages["retrieval"] = retrieval_trace
    multi_agent["stages"] = stages
    if retrieval_trace and retrieval_trace.get("status") == "required_but_unavailable":
        multi_agent["final_status"] = "insufficient_data"
    multi_agent["orchestration"] = dict(orchestration_trace or {})
    meta["multi_agent"] = multi_agent
    normalized["meta"] = meta
    validated = PostReportPayload.model_validate(normalized)
    return validated.model_dump()


def _build_invalid_output_fallback(
    *,
    post_id: int,
    signal_summary: dict[str, Any],
    error_message: str,
    retrieval_trace: dict[str, Any] | None = None,
    stage_traces: dict[str, Any] | None = None,
    orchestration_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stages: dict[str, Any] = dict(stage_traces or {})
    if retrieval_trace is not None:
        stages["retrieval"] = retrieval_trace
    fallback = PostReportPayload(
        status="failed",
        post_id=int(post_id),
        title="Не удалось собрать post_report",
        summary="Ответ модели не прошел строгую валидацию, поэтому сохранен безопасный fallback-отчет без генеративных выводов.",
        comment_count=int(signal_summary.get("comment_count") or 0),
        sentiment={
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "low",
        },
        topics=[],
        clusters=[],
        time_trends=[],
        risks=["Требуется повторная генерация post_report после невалидного ответа модели."],
        anomalies=["model_output_invalid"],
        representative_quotes=[
            sample.get("text", "")
            for sample in list(signal_summary.get("representative_samples") or [])[:POST_REPORT_PROMPT_MAX_QUOTES]
            if sample.get("text")
        ],
        confidence={"overall": "low", "reason": "model_output_invalid"},
        meta={
            "prompt_version": "post_report_v2",
            "input_mode": "preprocessed_signals_v1",
            "fallback_reason": "invalid_model_output",
            "validation_error": error_message[:500],
            "nlp_backend": dict(signal_summary.get("nlp_backend") or {}),
            "sentiment_hint": dict(signal_summary.get("sentiment_hint") or {}),
            "sentiment_backend": (
                ((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics") or {}).get("backend")
                or "fallback_neutral"
            ),
            "sentiment_model": (
                ((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics") or {}).get("model")
            ),
            "sentiment_model_configured": bool(
                ((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics") or {}).get("configured")
            ),
            "sentiment_transformers_available": bool(
                ((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics") or {}).get("transformers_available")
            ),
            "sentiment_fallback_reason": (
                ((signal_summary.get("nlp_backend") or {}).get("sentiment_diagnostics") or {}).get("fallback_reason")
            ),
            "article_sufficiency": signal_summary.get("article_sufficiency"),
            "comment_sufficiency": signal_summary.get("comment_sufficiency"),
            "sufficiency": signal_summary.get("sufficiency"),
            "discussion_state": signal_summary.get("discussion_state"),
            "weak_signal": signal_summary.get("weak_signal"),
            "public_opinion_strength": signal_summary.get("public_opinion_strength"),
            "evidence_candidates": signal_summary.get("evidence_candidates"),
            "multi_agent": {
                "epistemic_labels": [],
                "sufficiency": "insufficient",
                "stages": dict(stage_traces or {}),
                "review_iterations": 0,
                "final_status": "failed",
                "orchestration": dict(orchestration_trace or {}),
            },
        },
    )
    return fallback.model_dump()


def _stage_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_rerun_stage_name(stage_name: str | None) -> str | None:
    normalized = str(stage_name or "").strip().lower()
    if not normalized:
        return None
    if normalized not in POST_REPORT_STAGE_SEQUENCE:
        raise ValueError(f"Unsupported rerun stage: {stage_name}")
    return normalized


def _build_stage_timeout_budget(job_timeout_seconds: int | None) -> dict[str, int]:
    total = int(job_timeout_seconds or POST_REPORT_TIMEOUT_SECONDS)
    total = max(POST_REPORT_TIMEOUT_MIN_SECONDS, total)
    reserved = min(POST_REPORT_TIMEOUT_RESERVED_SECONDS, max(2, total // 6))
    synthesis_timeout = max(
        POST_REPORT_TIMEOUT_MIN_SECONDS,
        min(POST_REPORT_TIMEOUT_SECONDS, total - reserved),
    )
    return {
        "job_timeout_seconds": total,
        "reserved_seconds": reserved,
        "synthesis_timeout_seconds": synthesis_timeout,
    }


def _record_stage_execution(
    stage_traces: dict[str, Any],
    *,
    stage_name: str,
    stage_payload: dict[str, Any],
    rerun_requested: bool,
) -> dict[str, Any]:
    previous = stage_traces.get(stage_name)
    run_count = int(previous.get("run_count") or 0) + 1 if isinstance(previous, dict) else 1
    next_payload = dict(stage_payload)
    next_payload["run_count"] = run_count
    next_payload["rerun_requested"] = bool(rerun_requested)
    stage_traces[stage_name] = next_payload
    return next_payload


def _build_epistemic_labels(signal_summary: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, str]]:
    labels: list[dict[str, str]] = []
    sufficiency = str(signal_summary.get("sufficiency") or "insufficient")
    labels.append(
        {
            "label": "derived",
            "evidence": f"sufficiency={sufficiency}",
            "confidence": "medium" if sufficiency == "sufficient" else "low",
        }
    )
    if retrieval_required := bool(((payload.get("meta") or {}).get("multi_agent") or {}).get("stages", {}).get("retrieval", {}).get("required")):
        labels.append(
            {
                "label": "external",
                "evidence": "retrieval_required",
                "confidence": "low" if not bool(((payload.get("meta") or {}).get("multi_agent") or {}).get("stages", {}).get("retrieval", {}).get("provider_available")) else "medium",
            }
        )
    if bool(signal_summary.get("weak_signal")):
        labels.append(
            {
                "label": "uncertain",
                "evidence": "weak_internal_signal",
                "confidence": "high",
            }
        )
    return labels[:5]


def _append_unique_item(items: list[str], value: str | None) -> list[str]:
    normalized = _safe_text(value, limit=200) if isinstance(value, str) else ""
    if not normalized:
        return list(items)
    result = list(items)
    if normalized not in result:
        result.append(normalized)
    return result


def _review_target_status(*, signal_summary: dict[str, Any], retrieval_trace: dict[str, Any], reason_code: str) -> str:
    if reason_code == "retrieval_misuse":
        return "insufficient_data"
    sufficiency = str(signal_summary.get("sufficiency") or "insufficient")
    if sufficiency in {"insufficient", "weak_signal"}:
        return "insufficient_data"
    if retrieval_trace.get("required") and not retrieval_trace.get("provider_available"):
        return "insufficient_data"
    return "limited"


def _review_payload(
    payload: dict[str, Any],
    *,
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    iteration: int,
    max_iterations: int,
) -> dict[str, Any]:
    defects: list[str] = []
    rerun_stage: str | None = None
    status = str(payload.get("status") or "ready")
    confidence_overall = str(((payload.get("confidence") or {}).get("overall")) or "medium").lower()
    weak_signal = bool(signal_summary.get("weak_signal"))
    sufficiency = str(signal_summary.get("sufficiency") or "insufficient")
    retrieval_required = bool(retrieval_trace.get("required"))
    retrieval_available = bool(retrieval_trace.get("provider_available"))

    if retrieval_required and not retrieval_available and status == "ready":
        defects.append("retrieval_misuse")

    if status == "ready" and sufficiency == "insufficient":
        defects.append("sufficiency_misuse")

    if status == "ready" and weak_signal and confidence_overall == "high":
        defects.append("epistemic_violation")

    if defects and iteration < max_iterations and "retrieval_misuse" not in defects:
        rerun_stage = "public_opinion" if "sufficiency_misuse" in defects else "synthesis"
        decision = "rerun"
        target_status = status
        reason = f"reviewer_requested_rerun:{','.join(defects)}"
    elif defects:
        decision = "downgrade"
        target_status = _review_target_status(
            signal_summary=signal_summary,
            retrieval_trace=retrieval_trace,
            reason_code=defects[0],
        )
        reason = f"reviewer_exhausted:{','.join(defects)}" if iteration >= max_iterations else f"reviewer_downgraded:{','.join(defects)}"
    else:
        decision = "accept"
        target_status = status
        reason = "reviewer_accepted"

    return {
        "decision": decision,
        "defects": defects,
        "rerun_stage": rerun_stage,
        "target_status": target_status,
        "reason": reason,
    }


def _apply_review_decision_to_payload(
    payload: dict[str, Any],
    *,
    review: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(payload)
    decision = str(review.get("decision") or "accept")
    target_status = str(review.get("target_status") or updated.get("status") or "ready")

    if decision == "downgrade":
        updated["status"] = target_status
        confidence = dict(updated.get("confidence") or {})
        confidence["overall"] = "low" if target_status == "insufficient_data" else "medium"
        confidence["reason"] = (
            "Сводка ограничена внутренней проверкой качества и не может считаться полностью надёжной."
            if target_status == "limited"
            else "Данных недостаточно для надёжного итогового вывода после внутренней проверки."
        )
        updated["confidence"] = confidence
        updated["anomalies"] = _append_unique_item(list(updated.get("anomalies") or []), "reviewer_policy_downgrade")
    return updated


def _finalize_review_metadata(
    payload: dict[str, Any],
    *,
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    stage_traces: dict[str, Any],
    orchestration_trace: dict[str, Any],
    review_trace: dict[str, Any],
) -> dict[str, Any]:
    finalized = _validate_post_report_payload(
        payload,
        post_id=int(payload.get("post_id") or 0),
        signal_summary=signal_summary,
        retrieval_trace=retrieval_trace,
        stage_traces=stage_traces,
        orchestration_trace=orchestration_trace,
    )
    meta = dict(finalized.get("meta") or {})
    multi_agent = dict(meta.get("multi_agent") or {})
    multi_agent["review_iterations"] = int(review_trace.get("iterations") or 0)
    multi_agent["epistemic_labels"] = _build_epistemic_labels(signal_summary, finalized)
    multi_agent["final_status"] = str(finalized.get("status") or multi_agent.get("final_status") or "failed")
    meta["multi_agent"] = multi_agent
    finalized["meta"] = meta
    return finalized


async def _run_reviewer_stage(
    *,
    initial_payload: dict[str, Any],
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    stage_traces: dict[str, Any],
    orchestration_trace: dict[str, Any],
    rerun_stage_fn,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    review_trace: dict[str, Any] = {
        "status": "running",
        "started_at": _stage_timestamp(),
        "completed_at": None,
        "iterations": 0,
        "history": [],
    }
    payload = dict(initial_payload)

    for iteration in range(1, REVIEW_BUDGET_MAX_ITERATIONS + 1):
        review_trace["iterations"] = iteration
        review = _review_payload(
            payload,
            signal_summary=signal_summary,
            retrieval_trace=retrieval_trace,
            iteration=iteration,
            max_iterations=REVIEW_BUDGET_MAX_ITERATIONS,
        )
        history_entry = {
            "iteration": iteration,
            "decision": review["decision"],
            "defects": list(review.get("defects") or []),
            "rerun_stage": review.get("rerun_stage"),
            "target_status": review.get("target_status"),
            "reason": review.get("reason"),
            "started_at": _stage_timestamp(),
            "completed_at": _stage_timestamp(),
        }
        review_trace["history"].append(history_entry)

        if review["decision"] == "accept":
            review_trace["status"] = "completed"
            review_trace["decision"] = "accept"
            review_trace["completed_at"] = _stage_timestamp()
            return (
                _finalize_review_metadata(
                    payload,
                    signal_summary=signal_summary,
                    retrieval_trace=retrieval_trace,
                    stage_traces=stage_traces,
                    orchestration_trace=orchestration_trace,
                    review_trace=review_trace,
                ),
                review_trace,
            )

        if review["decision"] == "rerun":
            rerun_stage = str(review.get("rerun_stage") or "synthesis")
            rerun_payload = await rerun_stage_fn(rerun_stage)
            if rerun_payload is None:
                review_trace["status"] = "failed"
                review_trace["decision"] = "failed"
                review_trace["completed_at"] = _stage_timestamp()
                return None, review_trace
            payload = rerun_payload
            continue

        payload = _apply_review_decision_to_payload(payload, review=review)
        review_trace["status"] = "completed"
        review_trace["decision"] = "downgrade"
        review_trace["completed_at"] = _stage_timestamp()
        return (
            _finalize_review_metadata(
                payload,
                signal_summary=signal_summary,
                retrieval_trace=retrieval_trace,
                stage_traces=stage_traces,
                orchestration_trace=orchestration_trace,
                review_trace=review_trace,
            ),
            review_trace,
        )

    review_trace["status"] = "completed"
    review_trace["decision"] = "downgrade"
    review_trace["completed_at"] = _stage_timestamp()
    downgraded = _apply_review_decision_to_payload(
        payload,
        review={
            "decision": "downgrade",
            "target_status": _review_target_status(
                signal_summary=signal_summary,
                retrieval_trace=retrieval_trace,
                reason_code="review_exhaustion",
            ),
        },
    )
    return (
        _finalize_review_metadata(
            downgraded,
            signal_summary=signal_summary,
            retrieval_trace=retrieval_trace,
            stage_traces=stage_traces,
            orchestration_trace=orchestration_trace,
            review_trace=review_trace,
        ),
        review_trace,
    )


def _build_context_stage(
    signal_summary: dict[str, Any],
    *,
    channel: str,
    published_at_iso: str,
    views: Optional[int],
    post_text: str,
) -> dict[str, Any]:
    return {
        "status": "completed",
        "started_at": _stage_timestamp(),
        "completed_at": _stage_timestamp(),
        "channel": channel,
        "published_at": published_at_iso,
        "views": views,
        "post_excerpt": _short_text(post_text, max_chars_each=260),
        "comment_count": int(signal_summary.get("comment_count") or 0),
        "article_sufficiency": signal_summary.get("article_sufficiency"),
        "comment_sufficiency": signal_summary.get("comment_sufficiency"),
        "discussion_state": signal_summary.get("discussion_state"),
        "public_opinion_strength": signal_summary.get("public_opinion_strength"),
        "source": "preprocessed_signals",
    }


def _build_routing_stage(
    signal_summary: dict[str, Any],
    *,
    retrieval_trace: dict[str, Any],
) -> dict[str, Any]:
    discussion_state = str(signal_summary.get("discussion_state") or "")
    sufficiency = str(signal_summary.get("sufficiency") or "")
    if retrieval_trace.get("required"):
        route = "public_opinion_enhanced"
        reason = "retrieval_required_or_internal_signals_low"
    elif discussion_state in {"conflicted", "noisy"}:
        route = "public_opinion_focused"
        reason = "conflicted_or_noisy_discussion"
    elif sufficiency == "sufficient":
        route = "direct_synthesis"
        reason = "internal_signals_sufficient"
    else:
        route = "conservative_synthesis"
        reason = "limited_internal_signals"
    return {
        "status": "completed",
        "started_at": _stage_timestamp(),
        "completed_at": _stage_timestamp(),
        "route": route,
        "reason": reason,
        "retrieval_required": bool(retrieval_trace.get("required")),
        "retrieval_available": bool(retrieval_trace.get("provider_available")),
    }


def _build_expert_stage(
    signal_summary: dict[str, Any],
    *,
    routing_stage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "completed",
        "started_at": _stage_timestamp(),
        "completed_at": _stage_timestamp(),
        "focus_topics": [item.get("term") for item in list(signal_summary.get("top_keywords") or [])[:3]],
        "focus_entities": [
            value
            for bucket in (signal_summary.get("named_entities") or {}).values()
            for value in list(bucket)[:2]
        ],
        "route": routing_stage.get("route"),
        "insights": {
            "article_sufficiency": signal_summary.get("article_sufficiency"),
            "comment_sufficiency": signal_summary.get("comment_sufficiency"),
            "discussion_state": signal_summary.get("discussion_state"),
        },
    }


def _build_public_opinion_stage(
    signal_summary: dict[str, Any],
    *,
    expert_stage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "completed",
        "started_at": _stage_timestamp(),
        "completed_at": _stage_timestamp(),
        "discussion_state": signal_summary.get("discussion_state"),
        "weak_signal": signal_summary.get("weak_signal"),
        "public_opinion_strength": signal_summary.get("public_opinion_strength"),
        "expert_route": expert_stage.get("route"),
        "evidence_candidates": signal_summary.get("evidence_candidates"),
    }


async def _run_synthesis_stage(
    project: TgReportProject,
    *,
    channel: str,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    thread_comments: Optional[list[dict]],
    views: Optional[int],
    media_links: Optional[list[str]],
    config: Optional[ReportConfig],
    prompt: str,
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    stage_traces: dict[str, Any],
    synthesis_timeout_seconds: int,
    orchestration_trace: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    stage = {
        "status": "running",
        "started_at": _stage_timestamp(),
        "attempts": 0,
        "errors": [],
    }
    for attempt in range(POST_REPORT_MAX_RETRIES):
        stage["attempts"] = attempt + 1
        retry_note = ""
        if attempt:
            retry_note = (
                "\n\nPrevious response was invalid. Return one JSON object only, "
                "strictly matching the schema and labels."
            )
        try:
            response = await acompletion(
                model=project._llm_model,
                base_url=project._llm_base_url,
                api_key=project._llm_api_key,
                temperature=0.1,
                max_tokens=POST_REPORT_MAX_TOKENS,
                timeout=synthesis_timeout_seconds,
                messages=[
                    {"role": "system", "content": "You are a strict JSON report generator for Russian Telegram analytics."},
                    {"role": "user", "content": prompt + retry_note},
                ],
                metadata={
                    "feature": "post_report_v2",
                    "post_id": post_id,
                    "channel": channel,
                    "attempt": attempt + 1,
                },
            )
            text = _clean_model_output(_extract_response_text(response))
            payload = _extract_json_object(text)
            validated_payload = _validate_post_report_payload(
                payload,
                post_id=post_id,
                signal_summary=signal_summary,
                retrieval_trace=retrieval_trace,
                stage_traces=stage_traces,
                orchestration_trace=orchestration_trace,
            )
            stage["status"] = "completed"
            stage["completed_at"] = _stage_timestamp()
            stage["last_output_length"] = len(text)
            stage["timeout_seconds"] = synthesis_timeout_seconds
            return validated_payload, stage
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            stage["errors"].append(f"{type(exc).__name__}: {exc}")
            continue
    stage["status"] = "failed"
    stage["completed_at"] = _stage_timestamp()
    stage["failure_reason"] = "invalid_model_output"
    stage["timeout_seconds"] = synthesis_timeout_seconds
    return None, stage


async def _run_post_report_orchestration(
    project: TgReportProject,
    *,
    channel: str,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    thread_comments: Optional[list[dict]],
    views: Optional[int],
    media_links: Optional[list[str]],
    config: Optional[ReportConfig],
    prompt: str,
    signal_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    job_timeout_seconds: int | None = None,
    rerun_stage: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    normalized_rerun_stage = _normalize_rerun_stage_name(rerun_stage)
    timeout_budget = _build_stage_timeout_budget(job_timeout_seconds)
    stage_traces: dict[str, Any] = {}
    orchestration_trace: dict[str, Any] = {
        "sequence": list(POST_REPORT_STAGE_SEQUENCE),
        "reviewer_enabled": True,
        "requested_rerun_stage": normalized_rerun_stage,
        "executed_rerun_stage": None,
        "timeout_budget": timeout_budget,
    }

    async def _execute_from(stage_name: str | None = None) -> dict[str, Any] | None:
        rerun_mode = stage_name is not None
        if rerun_mode:
            orchestration_trace["executed_rerun_stage"] = stage_name

        start_index = POST_REPORT_STAGE_SEQUENCE.index(stage_name) if stage_name else 0
        result_payload: dict[str, Any] | None = None
        for current_stage in POST_REPORT_STAGE_SEQUENCE[start_index:]:
            if current_stage == "context":
                _record_stage_execution(
                    stage_traces,
                    stage_name="context",
                    stage_payload=_build_context_stage(
                        signal_summary,
                        channel=channel,
                        published_at_iso=published_at_iso,
                        views=views,
                        post_text=post_text,
                    ),
                    rerun_requested=rerun_mode,
                )
            elif current_stage == "routing":
                _record_stage_execution(
                    stage_traces,
                    stage_name="routing",
                    stage_payload=_build_routing_stage(signal_summary, retrieval_trace=retrieval_trace),
                    rerun_requested=rerun_mode,
                )
            elif current_stage == "expert":
                _record_stage_execution(
                    stage_traces,
                    stage_name="expert",
                    stage_payload=_build_expert_stage(signal_summary, routing_stage=stage_traces["routing"]),
                    rerun_requested=rerun_mode,
                )
            elif current_stage == "public_opinion":
                _record_stage_execution(
                    stage_traces,
                    stage_name="public_opinion",
                    stage_payload=_build_public_opinion_stage(signal_summary, expert_stage=stage_traces["expert"]),
                    rerun_requested=rerun_mode,
                )
            elif current_stage == "synthesis":
                result_payload, synthesis_stage = await _run_synthesis_stage(
                    project,
                    channel=channel,
                    post_id=post_id,
                    published_at_iso=published_at_iso,
                    post_text=post_text,
                    comments=comments,
                    thread_comments=thread_comments,
                    views=views,
                    media_links=media_links,
                    config=config,
                    prompt=prompt,
                    signal_summary=signal_summary,
                    retrieval_trace=retrieval_trace,
                    stage_traces=stage_traces,
                    synthesis_timeout_seconds=timeout_budget["synthesis_timeout_seconds"],
                    orchestration_trace=orchestration_trace,
                )
                _record_stage_execution(
                    stage_traces,
                    stage_name="synthesis",
                    stage_payload=synthesis_stage,
                    rerun_requested=rerun_mode,
                )
        return result_payload

    result = await _execute_from()
    if normalized_rerun_stage is not None:
        result = await _execute_from(normalized_rerun_stage)
    if result is None:
        return result, stage_traces, orchestration_trace

    reviewed_result, reviewer_stage = await _run_reviewer_stage(
        initial_payload=result,
        signal_summary=signal_summary,
        retrieval_trace=retrieval_trace,
        stage_traces=stage_traces,
        orchestration_trace=orchestration_trace,
        rerun_stage_fn=_execute_from,
    )
    _record_stage_execution(
        stage_traces,
        stage_name=POST_REPORT_REVIEWER_STAGE,
        stage_payload=reviewer_stage,
        rerun_requested=bool(reviewer_stage.get("decision") == "rerun"),
    )
    if reviewed_result is not None:
        reviewed_result = _finalize_review_metadata(
            reviewed_result,
            signal_summary=signal_summary,
            retrieval_trace=retrieval_trace,
            stage_traces=stage_traces,
            orchestration_trace=orchestration_trace,
            review_trace=reviewer_stage,
        )
    return reviewed_result, stage_traces, orchestration_trace


def _format_signal_summary(signal_summary: dict[str, Any]) -> str:
    return json.dumps(signal_summary, ensure_ascii=False, indent=2)


def _format_comments_items(comments: list[str], max_chars_each: int = 600) -> str:
    lines: list[str] = []
    for idx, c in enumerate(comments, start=1):
        if not c:
            continue
        text = c.strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > max_chars_each:
            text = text[: max_chars_each - 1] + "..."
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _short_text(text: str, max_chars_each: int = 400) -> str:
    value = (text or "").strip().replace("\n", " ")
    if len(value) > max_chars_each:
        value = value[: max_chars_each - 1] + "..."
    return value


def _format_thread_nodes_json(thread_comments: list[dict], max_chars_each: int = 400) -> str:
    items: list[dict] = []
    for c in thread_comments:
        text = _short_text(str(c.get("text", "")), max_chars_each=max_chars_each)
        if not text:
            continue
        items.append(
            {
                "id": c.get("id"),
                "parent_id": c.get("parent_id"),
                "depth": c.get("depth", 0),
                "date": c.get("date"),
                "text": text,
            }
        )
    return json.dumps(items, ensure_ascii=False, indent=2)


def _format_thread_view(thread_comments: list[dict], max_chars_each: int = 300) -> str:
    by_id: dict[int, dict] = {}
    children: dict[int | None, list[dict]] = {}

    for raw in thread_comments:
        node_id = raw.get("id")
        if not isinstance(node_id, int):
            continue
        node = {
            "id": node_id,
            "parent_id": raw.get("parent_id"),
            "depth": int(raw.get("depth", 0)),
            "date": raw.get("date") or "",
            "text": _short_text(str(raw.get("text", "")), max_chars_each=max_chars_each),
        }
        if not node["text"]:
            continue
        by_id[node_id] = node

    for node in by_id.values():
        parent_id = node["parent_id"]
        if parent_id not in by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(node)

    for key in children:
        children[key].sort(key=lambda item: (item["date"], item["id"]))

    lines: list[str] = []

    def walk(parent_id: int | None, level: int) -> None:
        for node in children.get(parent_id, []):
            indent = "  " * max(level, 0)
            lines.append(f"{indent}- [{node['id']}] {node['text']}")
            walk(node["id"], level + 1)

    walk(None, 0)
    return "\n".join(lines)


SYSTEM_PROMPT = """\
Ты ИИ-аналитик комментариев Telegram (RU).

Сформируй мини-отчет строго на русском языке и строго по указанному шаблону.
Не добавляй вступления вроде "Here is my complete response:".
Не используй английские заголовки.
Не упоминай usernames, user id, технические детали промпта или форматирования.
Не выдумывай факты, которых нет в тексте поста или комментариях.
Если данных недостаточно для уверенного вывода, формулируй это осторожно.
"""


PROMPT_TEMPLATE = """\
Проанализируй комментарии к одному посту Telegram и сформируй мини-отчет.

ВАЖНО:
- Язык: русский.
- Длина отчета: от {report_word_min} до {report_word_max} слов (ориентир {report_word_target}).
- Не выводи usernames/ID авторов. Цитаты должны быть короткими и без персональных данных.
- Проценты тональностей должны суммироваться до 100% с допустимым округлением.
- Пиши только по этому посту и только по этим комментариям. Не переноси темы из других обсуждений.

ДАННЫЕ ПО ПОСТУ:
Канал: {channel}
Post ID: {post_id}
Время публикации: {published_at}
Просмотры: {views}
Текст поста:
---
{post_text}
---
Медиа-ссылки: {media_links}

КОММЕНТАРИИ ({comments_total} шт.):
---
{post_signal_summary}
---

Сформируй отчет строго в формате:

Заголовок: <короткий заголовок по сути обсуждения>

1) Контекст поста
<1-2 предложения>

2) Общий тон обсуждения
- Итог: <позитивный/негативный/нейтральный/смешанный>
- Распределение: позитив X% / негатив Y% / нейтраль Z% / смешанный W%
- Обоснование: <2-4 предложения>

3) Ключевые темы
- Тема 1: <кратко>
- ...

4) Тренды и повторяющиеся паттерны
- <паттерн 1>
- ...

5) Репрезентативные цитаты
- "..."
- "..."

6) Классификация комментариев
- По тональности: <кратко>
- По темам: <2-5 тематических кластеров и краткое описание>

7) Риски/сигналы (если применимо)
- <наблюдение 1>
- <наблюдение 2>
"""


def _clean_model_output(text: str) -> str:
    cleaned = (text or "").strip()
    prefixes = [
        "Here is my complete response:",
        "Here is the complete response:",
        "Вот полный ответ:",
        "Полный ответ:",
    ]
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def _extract_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


class TgReportProject:
    """
    Stateless wrapper over a direct LiteLLM call.
    """

    def __init__(
        self,
        *,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        process: Any = None,
        verbose: bool = False,
        memory: bool = False,
        cache: bool = False,
        full_output: bool = False,
        share_crew: bool = False,
        agent_max_iter: int = 2,
        agent_max_rpm: int = 30,
    ) -> None:
        report_llm_settings = load_report_llm_settings()
        self._llm_model = llm_model or report_llm_settings.llm_model
        self._llm_base_url = llm_base_url or report_llm_settings.llm_base_url
        self._llm_api_key = llm_api_key or report_llm_settings.llm_api_key
        self._verbose = verbose
        self._memory = memory
        self._cache = cache
        self._full_output = full_output
        self._share_crew = share_crew
        self._process = process
        self._agent_max_iter = agent_max_iter
        self._agent_max_rpm = agent_max_rpm

        # Keep LiteLLM stateless and quiet for local pipeline runs.
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        litellm.telemetry = False
        litellm.success_callback = []
        litellm.failure_callback = []
        litellm.service_callback = []
        _disable_litellm_cold_storage_logging()

    @classmethod
    def from_settings(cls) -> "TgReportProject":
        return create_report_project()

    async def generate_report(
        self,
        *,
        channel: str,
        post_id: int,
        published_at_iso: str,
        post_text: str,
        comments: list[str],
        thread_comments: Optional[list[dict]] = None,
        views: Optional[int] = None,
        media_links: Optional[list[str]] = None,
        config: Optional[ReportConfig] = None,
    ) -> str:
        cfg = config or ReportConfig()

        thread_comments = thread_comments or []
        comments_count = len(thread_comments) if thread_comments else len(comments)

        if comments_count < cfg.min_comments:
            return (
                "STATUS: SKIPPED_MIN_COMMENTS\n"
                f"REASON: недостаточно комментариев для анализа ({comments_count})"
            )

        signal_summary = build_post_signal_summary(
            post_text=post_text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=views,
        )

        prompt = PROMPT_TEMPLATE.format(
            channel=channel,
            post_id=post_id,
            published_at=published_at_iso,
            views="" if views is None else views,
            post_text=post_text or "",
            media_links=", ".join(media_links or []),
            comments_total=signal_summary["comment_count"],
            post_signal_summary=_format_signal_summary(signal_summary),
            report_word_min=cfg.report_word_min,
            report_word_max=cfg.report_word_max,
            report_word_target=cfg.report_word_target,
        )

        response = await acompletion(
            model=self._llm_model,
            base_url=self._llm_base_url,
            api_key=self._llm_api_key,
            temperature=0.2,
            max_tokens=900,
            timeout=300,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            metadata={"feature": "post_report", "post_id": post_id, "channel": channel},
        )
        return _clean_model_output(_extract_response_text(response))

    async def generate_post_report_payload(
        self,
        *,
        channel: str,
        post_id: int,
        published_at_iso: str,
        post_text: str,
        comments: list[str],
        thread_comments: Optional[list[dict]] = None,
        views: Optional[int] = None,
        media_links: Optional[list[str]] = None,
        config: Optional[ReportConfig] = None,
        job_timeout_seconds: int | None = None,
        rerun_stage: str | None = None,
    ) -> dict[str, Any]:
        cfg = config or ReportConfig()
        thread_comments = thread_comments or []
        comments_count = len(thread_comments) if thread_comments else len(comments)
        if comments_count < cfg.min_comments:
            sentiment_diagnostics = _build_sentiment_diagnostics(
                {
                    "dominant_hint": "neutral",
                    "distribution_hint": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                    "confidence": "low",
                    "backend": "fallback_neutral",
                }
            )
            return {
                "type": "post_report_v2",
                "status": "skipped_min_comments",
                "post_id": post_id,
                "title": "Недостаточно комментариев",
                "summary": f"Недостаточно комментариев для устойчивого анализа ({comments_count}).",
                "comment_count": comments_count,
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                    "confidence": "low",
                },
                "topics": [],
                "clusters": [],
                "time_trends": [],
                "risks": [],
                "anomalies": [],
                "representative_quotes": [],
                "confidence": {"overall": "low", "reason": "Недостаточно комментариев."},
                "meta": {
                    "prompt_version": "post_report_v2",
                    "sentiment_backend": sentiment_diagnostics.get("backend"),
                    "sentiment_model": sentiment_diagnostics.get("model"),
                    "sentiment_model_configured": bool(sentiment_diagnostics.get("configured")),
                    "sentiment_transformers_available": bool(sentiment_diagnostics.get("transformers_available")),
                    "sentiment_fallback_reason": sentiment_diagnostics.get("fallback_reason"),
                    "multi_agent": {
                        "epistemic_labels": [],
                        "sufficiency": "insufficient",
                        "stages": {},
                        "review_iterations": 0,
                        "final_status": "insufficient_data",
                    },
                },
            }

        signal_summary = build_post_signal_summary(
            post_text=post_text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=views,
        )
        retrieval_trace = _evaluate_retrieval_policy(signal_summary=signal_summary, post_text=post_text or "")
        prompt = _build_post_report_prompt(
            channel=channel,
            post_id=post_id,
            published_at_iso=published_at_iso,
            post_text=post_text,
            views=views,
            media_links=media_links,
            signal_summary=signal_summary,
        )

        result, stage_traces, orchestration_trace = await _run_post_report_orchestration(
            self,
            channel=channel,
            post_id=post_id,
            published_at_iso=published_at_iso,
            post_text=post_text,
            comments=comments,
            thread_comments=thread_comments,
            views=views,
            media_links=media_links,
            config=cfg,
            prompt=prompt,
            signal_summary=signal_summary,
            retrieval_trace=retrieval_trace,
            job_timeout_seconds=job_timeout_seconds,
            rerun_stage=rerun_stage,
        )

        if result is not None:
            return _validate_post_report_payload(
                result,
                post_id=post_id,
                signal_summary=signal_summary,
                retrieval_trace=retrieval_trace,
                stage_traces=stage_traces,
                orchestration_trace=orchestration_trace,
            )

        return _build_invalid_output_fallback(
            post_id=post_id,
            signal_summary=signal_summary,
            error_message="invalid_model_output_or_validation_failure",
            retrieval_trace=retrieval_trace,
            stage_traces=stage_traces,
            orchestration_trace=orchestration_trace,
        )


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Empty model output")
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(cleaned[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Model output is not a JSON object")


def create_report_project() -> TgReportProject:
    report_llm_settings = load_report_llm_settings()
    return TgReportProject(
        llm_model=report_llm_settings.llm_model,
        llm_base_url=report_llm_settings.llm_base_url,
        llm_api_key=report_llm_settings.llm_api_key,
    )


@lru_cache(maxsize=1)
def get_report_project() -> TgReportProject:
    return create_report_project()
