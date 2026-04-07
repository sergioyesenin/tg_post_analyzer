from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
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

Task: analyze one Telegram post using normalized comment signals and deterministic representative samples, then build a compact structured report.
Use only these sentiment labels: positive, negative, neutral.
Do not invent facts. If confidence is low, say so in confidence.reason.
Treat representative_samples as evidence examples, and treat post_signal_summary as the primary source for counts, structure, topic hints and entities.
If the evidence is weak or partial, summarize conservatively.
The resulting payload must be sufficient to render a structured Russian mini-report with these sections:
- context of the post,
- overall tone of discussion with percentage sentiment split,
- key topics,
- trends and recurring patterns,
- representative quotes,
- comment classification by sentiment,
- thematic classification of comments,
- risks/signals when applicable.
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
    normalized["meta"] = meta
    validated = PostReportPayload.model_validate(normalized)
    return validated.model_dump()


def _build_invalid_output_fallback(
    *,
    post_id: int,
    signal_summary: dict[str, Any],
    error_message: str,
) -> dict[str, Any]:
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
        },
    )
    return fallback.model_dump()

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
                },
            }

        signal_summary = build_post_signal_summary(
            post_text=post_text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=views,
        )
        prompt = _build_post_report_prompt(
            channel=channel,
            post_id=post_id,
            published_at_iso=published_at_iso,
            post_text=post_text,
            views=views,
            media_links=media_links,
            signal_summary=signal_summary,
        )

        last_error: Exception | None = None
        for attempt in range(POST_REPORT_MAX_RETRIES):
            try:
                retry_note = ""
                if attempt:
                    retry_note = (
                        "\n\nPrevious response was invalid. Return one JSON object only, "
                        "strictly matching the schema and labels."
                    )
                response = await acompletion(
                    model=self._llm_model,
                    base_url=self._llm_base_url,
                    api_key=self._llm_api_key,
                    temperature=0.1,
                    max_tokens=POST_REPORT_MAX_TOKENS,
                    timeout=POST_REPORT_TIMEOUT_SECONDS,
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
                return _validate_post_report_payload(
                    payload,
                    post_id=post_id,
                    signal_summary=signal_summary,
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                continue

        return _build_invalid_output_fallback(
            post_id=post_id,
            signal_summary=signal_summary,
            error_message=f"{type(last_error).__name__}: {last_error}" if last_error is not None else "unknown_validation_error",
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
