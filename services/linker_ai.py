from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task

from config import settings

ALLOWED_LINK_TYPES = {
    "DUPLICATE",
    "NEAR_DUPLICATE",
    "SAME_EVENT",
    "UPDATE",
    "REFUTES",
    "CITES_SOURCE",
    "CAUSE_EFFECT",
    "TRANSLATION",
    "UNRELATED",
}

PROMPT_TEMPLATE = """Ты строгий классификатор связей между постами Telegram.
Верни только JSON. Без markdown и пояснений.

Задача:
Определи, связаны ли два поста. Если связаны, классифицируй тип связи.

Допустимые значения link_type:
DUPLICATE, NEAR_DUPLICATE, SAME_EVENT, UPDATE, REFUTES, CITES_SOURCE, CAUSE_EFFECT, TRANSLATION, UNRELATED

Правила:
- DUPLICATE: почти полностью идентичный контент.
- NEAR_DUPLICATE: то же утверждение/контент с небольшими правками.
- SAME_EVENT: одно и то же реальное событие, но разные формулировки.
- UPDATE: один пост обновляет информацию другого.
- REFUTES: один пост опровергает/исправляет утверждение другого.
- CITES_SOURCE: один пост ссылается на другой как источник.
- CAUSE_EFFECT: между утверждениями есть причинно-следственная связь.
- TRANSLATION: одинаковый контент на другом языке.
- UNRELATED: содержательной связи нет.

Схема выходного JSON:
{{
  "is_related": boolean,
  "link_type": "string",
  "confidence": number,
  "reason": "короткая строка",
  "shared_facts": ["факт 1", "факт 2"]
}}

Уверенность должна быть в диапазоне [0, 1].
Если есть сомнения, установи is_related=false и link_type="UNRELATED".
Если is_related=true, укажи минимум 2 конкретных общих факта в shared_facts.

Пост A:
channel_id={a_channel_id}
published_at={a_date}
text:
{a_text}

Пост B:
channel_id={b_channel_id}
published_at={b_date}
text:
{b_text}

Эвристические подсказки (могут ошибаться, проверь семантически):
text_jaccard={text_jaccard}
entities_jaccard={entities_jaccard}
hash_equal={hash_equal}
shared_anchor_count={shared_anchor_count}
"""


@dataclass(frozen=True)
class LinkDecision:
    is_related: bool
    link_type: str
    confidence: float
    reason: str
    shared_facts: list[str]


class AiLinkClassifier:
    def __init__(
        self,
        *,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
    ) -> None:
        self._llm = LLM(
            model=llm_model or settings.LINKER_LLM_MODEL,
            base_url=llm_base_url or settings.LINKER_LLM_BASE_URL,
            api_key=llm_api_key or settings.LINKER_LLM_API_KEY,
        )
        self._agent = Agent(
            role="Классификатор связей",
            goal="Классифицировать связь между двумя постами Telegram и вернуть строгий JSON",
            backstory="Ты точен и консервативен. Не придумываешь факты и типы связей.",
            allow_delegation=False,
            verbose=False,
            llm=self._llm,
            tools=[],
            memory=False,
            cache=False,
            max_iter=1,
            max_rpm=30,
        )

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        value = (text or "").strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        start = value.find("{")
        end = value.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        snippet = value[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _normalize_decision(payload: dict) -> LinkDecision:
        is_related = bool(payload.get("is_related", False))
        link_type = str(payload.get("link_type", "UNRELATED")).upper().strip()
        if link_type not in ALLOWED_LINK_TYPES:
            link_type = "UNRELATED"

        confidence_raw = payload.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reason = str(payload.get("reason", "")).strip()[:500]
        shared_facts_raw = payload.get("shared_facts", [])
        shared_facts: list[str] = []
        if isinstance(shared_facts_raw, list):
            for item in shared_facts_raw[:5]:
                text = str(item).strip()
                if text:
                    shared_facts.append(text[:200])

        if link_type == "UNRELATED":
            is_related = False
        return LinkDecision(
            is_related=is_related,
            link_type=link_type,
            confidence=confidence,
            reason=reason,
            shared_facts=shared_facts,
        )

    async def classify_pair(
        self,
        *,
        post_a_text: str,
        post_b_text: str,
        post_a_channel_id: int,
        post_b_channel_id: int,
        post_a_date: datetime,
        post_b_date: datetime,
        text_jaccard: float,
        entities_jaccard: float,
        hash_equal: bool,
        shared_anchor_count: int = 0,
    ) -> LinkDecision:
        prompt = PROMPT_TEMPLATE.format(
            a_channel_id=post_a_channel_id,
            a_date=post_a_date.isoformat(),
            a_text=post_a_text or "",
            b_channel_id=post_b_channel_id,
            b_date=post_b_date.isoformat(),
            b_text=post_b_text or "",
            text_jaccard=round(text_jaccard, 4),
            entities_jaccard=round(entities_jaccard, 4),
            hash_equal=str(hash_equal).lower(),
            shared_anchor_count=shared_anchor_count,
        )

        task_obj = Task(
            description=prompt,
            expected_output="Строгий JSON-объект с полями is_related/link_type/confidence/reason/shared_facts",
            agent=self._agent,
        )
        crew = Crew(
            agents=[self._agent],
            tasks=[task_obj],
            process=Process.sequential,
            verbose=False,
            memory=False,
            cache=False,
        )

        kickoff_async = getattr(crew, "kickoff_async", None)
        if callable(kickoff_async):
            raw_result = await kickoff_async()
        else:
            raw_result = crew.kickoff()

        parsed = self._extract_json(str(raw_result))
        if parsed is None:
            return LinkDecision(
                is_related=False,
                link_type="UNRELATED",
                confidence=0.0,
                reason="model_output_not_json",
                shared_facts=[],
            )
        return self._normalize_decision(parsed)
