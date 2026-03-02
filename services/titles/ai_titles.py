from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from crewai import Agent, Crew, LLM, Process, Task

from config import settings
from db.models import Post, PostFact

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_-]{3,}")
BLOCKED_PATTERNS = [
    re.compile(r"^\s*here\s+are\b", re.IGNORECASE),
    re.compile(r"^\s*here\s+is\b", re.IGNORECASE),
    re.compile(r"^\s*ответ[ы]?:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*final\s+answer\b", re.IGNORECASE),
    re.compile(r"^\s*response\b", re.IGNORECASE),
]


def _title_tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or "")}


def _looks_like_noise(title: str) -> bool:
    clean = (title or "").strip()
    if not clean:
        return True
    if len(_title_tokens(clean)) == 0:
        return True
    if len(clean) < 6:
        return True
    return any(p.search(clean) for p in BLOCKED_PATTERNS)


def _passes_context_overlap(title: str, context_tokens: set[str]) -> bool:
    if not context_tokens:
        return True
    tt = _title_tokens(title)
    if not tt:
        return False
    return len(tt & context_tokens) >= 1


def _clip(text: str | None, limit: int = 220) -> str:
    value = (text or "").strip().replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _fallback_event_title(posts: list[Post], facts_map: dict[int, PostFact]) -> str:
    if posts:
        first = _clip(posts[0].text, 90)
        if first:
            return first
    entities: list[str] = []
    for post in posts[:3]:
        facts = facts_map.get(post.id)
        if not facts or not isinstance(facts.entities_json, dict):
            continue
        entities.extend(str(x) for x in facts.entities_json.get("entities", [])[:2])
    if entities:
        return "Событие: " + ", ".join(entities[:3])
    return "Событие без названия"


def _fallback_process_title(event_titles: Iterable[str]) -> str:
    titles = [t for t in event_titles if t]
    if titles:
        return f"Процесс: {titles[0][:70]}"
    return "Процесс без названия"


class AITitleGenerator:
    def __init__(self) -> None:
        self._llm = LLM(
            model=settings.LINKER_LLM_MODEL,
            base_url=settings.LINKER_LLM_BASE_URL,
            api_key=settings.LINKER_LLM_API_KEY,
        )
        self._agent = Agent(
            role="Генератор коротких заголовков",
            goal="Создавать короткие понятные заголовки на русском языке без выдуманных фактов",
            backstory=(
                "Ты формируешь заголовки для событий и процессов по данным постов. "
                "Запрещено придумывать факты, которых нет в исходных данных."
            ),
            allow_delegation=False,
            verbose=False,
            llm=self._llm,
            tools=[],
            memory=False,
            cache=False,
            max_iter=1,
        )

    async def _title_from_prompt(self, prompt: str, fallback: str) -> str:
        if not settings.TITLES_AI_ENABLED:
            return fallback
        task = Task(
            description=prompt,
            expected_output="Только одна строка: короткий заголовок (до 100 символов), без кавычек и пояснений.",
            agent=self._agent,
        )
        crew = Crew(
            agents=[self._agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
            memory=False,
            cache=False,
        )
        try:
            kickoff_async = getattr(crew, "kickoff_async", None)
            raw = await kickoff_async() if callable(kickoff_async) else crew.kickoff()
            title = str(raw).strip().splitlines()[0].strip()
            if not title:
                return fallback
            return title[:100]
        except Exception:
            return fallback

    def _sanitize_title(self, title: str, *, fallback: str, context_tokens: set[str]) -> str:
        clean = (title or "").strip().strip("\"'`")
        clean = re.sub(r"\s+", " ", clean)
        if _looks_like_noise(clean):
            return fallback
        if not _passes_context_overlap(clean, context_tokens):
            return fallback
        if len(clean) > 100:
            clean = clean[:100].rstrip()
        return clean or fallback

    async def event_title(self, posts: list[Post], facts_map: dict[int, PostFact]) -> str:
        fallback = _fallback_event_title(posts, facts_map)
        limited_posts = posts[: settings.TITLES_AI_MAX_INPUT_POSTS]
        rows = []
        context_tokens = set()
        for post in limited_posts:
            facts = facts_map.get(post.id)
            entities = []
            if facts and isinstance(facts.entities_json, dict):
                entities = facts.entities_json.get("entities", [])[:4]
                context_tokens.update(str(e).lower() for e in facts.entities_json.get("entities", []))
                context_tokens.update(str(e).lower() for e in facts.entities_json.get("tickers", []))
                context_tokens.update(str(e).lower() for e in facts.entities_json.get("places", []))
            context_tokens.update(_title_tokens(post.text or ""))
            rows.append(
                f"- post_id={post.id}; date={post.date.isoformat()}; entities={entities}; text={_clip(post.text, 240)}"
            )
        prompt = (
            "Сгенерируй короткий осмысленный заголовок события для пользователя.\n"
            "Требования:\n"
            "- Русский язык.\n"
            "- До 100 символов.\n"
            "- По фактам из входных данных, без выдумок.\n"
            "- Без префиксов типа 'Заголовок:'.\n\n"
            f"Посты события ({len(posts)} шт):\n" + "\n".join(rows)
        )
        raw_title = await self._title_from_prompt(prompt, fallback)
        return self._sanitize_title(raw_title, fallback=fallback, context_tokens=context_tokens)

    async def process_title(self, events: list[tuple[int, str, datetime | None, datetime | None]]) -> str:
        fallback = _fallback_process_title(title for _, title, _, _ in events)
        context_tokens = set()
        rows = [
            f"- event_id={event_id}; title={_clip(title, 90)}; started_at={started_at}; ended_at={ended_at}"
            for event_id, title, started_at, ended_at in events[: settings.TITLES_AI_MAX_INPUT_POSTS]
        ]
        for _, title, _, _ in events[: settings.TITLES_AI_MAX_INPUT_POSTS]:
            context_tokens.update(_title_tokens(title))
        prompt = (
            "Сгенерируй короткий осмысленный заголовок процесса для пользователя.\n"
            "Требования:\n"
            "- Русский язык.\n"
            "- До 100 символов.\n"
            "- Отрази причинно-следственную или хронологическую динамику, если она есть.\n"
            "- Без выдумок и без префиксов.\n\n"
            "События процесса:\n"
            + "\n".join(rows)
        )
        raw_title = await self._title_from_prompt(prompt, fallback)
        return self._sanitize_title(raw_title, fallback=fallback, context_tokens=context_tokens)
