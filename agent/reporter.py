from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from crewai import Agent, Crew, Process, Task, LLM


@dataclass(frozen=True)
class ReportConfig:
    min_comments: int = 20
    report_word_target: int = 350
    report_word_min: int = 200
    report_word_max: int = 500


def _format_comments_items(comments: list[str], max_chars_each: int = 600) -> str:
    lines: list[str] = []
    for idx, c in enumerate(comments, start=1):
        if not c:
            continue
        text = c.strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > max_chars_each:
            text = text[: max_chars_each - 1] + "…"
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


TASK_EXPECTED_OUTPUT = (
    "Структурированный текст на русском, 200–500 слов (конфигурируемо), со следующими разделами:\n"
    "1) Контекст поста (1–2 предложения)\n"
    "2) Общий тон обсуждения + процентное распределение тональностей\n"
    "3) Ключевые темы (3–7 пунктов)\n"
    "4) Тренды/паттерны (2–5 пунктов)\n"
    "5) Репрезентативные цитаты (3–5 коротких, без usernames)\n"
    "6) Классификация комментариев: по тональности + по темам (краткие итоги)\n"
    "7) Риски/сигналы (если есть): поляризация, координация, повторяемость тезисов (без категоричных выводов)\n"
)

PROMPT_TEMPLATE = """\
Ты анализируешь комментарии к одному посту Telegram и формируешь мини-отчет.

ВАЖНО:
- Язык: русский.
- Длина отчета: от {report_word_min} до {report_word_max} слов (ориентир {report_word_target}).
- Не выводи usernames/ID авторов. Цитаты — короткие, без персональных данных.
- Проценты тональностей должны суммироваться до 100% (допускается округление).

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
{comments_items}
---

Сформируй отчет строго в формате:

Заголовок: <короткий заголовок по сути обсуждения>

1) Контекст поста
<1–2 предложения>

2) Общий тон обсуждения
- Итог: <позитивный/негативный/нейтральный/смешанный>
- Распределение: позитив X% / негатив Y% / нейтрал Z% / смешанный W%
- Обоснование: <2–4 предложения>

3) Ключевые темы
- Тема 1: <кратко>
- ...
(3–7 пунктов)

4) Тренды и повторяющиеся паттерны
- <паттерн 1>
- ...
(2–5 пунктов)

5) Репрезентативные цитаты
- "..."
- "..."
(3–5 цитат)

6) Классификация комментариев
- По тональности: <кратко, что характерно для каждой группы>
- По темам: <2–5 тематических кластеров и их краткое описание>

7) Риски/сигналы (если применимо)
- <наблюдение 1>
- <наблюдение 2>
"""


class TgReportProject:
    """
    Простой класс без CrewBase — меньше магии, меньше ошибок.
    """

    def __init__(
        self,
        *,
        llm_model: str = "ollama/llama3:8b-instruct-q4_K_M",
        llm_base_url: Optional[str] = "http://localhost:11434",
        llm_api_key: Optional[str] = None,
        process: Process = Process.sequential,
        verbose: bool = False,
        memory: bool = False,
        cache: bool = False,
        full_output: bool = False,
        share_crew: bool = False,
        agent_max_iter: int = 2,
        agent_max_rpm: int = 30,
    ) -> None:
        self._process = process
        self._verbose = verbose
        self._memory = memory
        self._cache = cache
        self._full_output = full_output
        self._share_crew = share_crew

        self._agent_max_iter = agent_max_iter
        self._agent_max_rpm = agent_max_rpm

        self._llm = LLM(
            model=llm_model,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )

        # ленивые поля
        self._agent: Optional[Agent] = None

    def _get_agent(self) -> Agent:
        if self._agent is not None:
            return self._agent

        self._agent = Agent(
            role="ИИ-аналитик комментариев Telegram (RU)",
            goal=(
                "Генерировать структурированные мини-отчеты по одному посту Telegram на основе комментариев: "
                "тональность + проценты, ключевые темы, тренды/паттерны, цитаты, классификации."
            ),
            backstory=(
                "Ты работаешь в аналитическом контуре. Следуешь формату, не выводишь персональные данные, "
                "аккуратно формулируешь выводы. Понимаешь сленг/эмодзи/RU-EN."
            ),
            allow_delegation=False,
            verbose=False,
            llm=self._llm,
            tools=[],
            memory=False,
            cache=False,
            max_iter=self._agent_max_iter,
            max_rpm=self._agent_max_rpm,
        )
        return self._agent

    async def generate_report(
        self,
        *,
        channel: str,
        post_id: int,
        published_at_iso: str,
        post_text: str,
        comments: list[str],
        views: Optional[int] = None,
        media_links: Optional[list[str]] = None,
        config: Optional[ReportConfig] = None,
    ) -> str:
        cfg = config or ReportConfig()

        if len(comments) < cfg.min_comments:
            return (
                "STATUS: SKIPPED_MIN_COMMENTS\n"
                f"REASON: недостаточно комментариев для анализа ({len(comments)})"
            )

        prompt = PROMPT_TEMPLATE.format(
            channel=channel,
            post_id=post_id,
            published_at=published_at_iso,
            views="" if views is None else views,
            post_text=post_text or "",
            media_links=", ".join(media_links or []),
            comments_total=len(comments),
            comments_items=_format_comments_items(comments),
            report_word_min=cfg.report_word_min,
            report_word_max=cfg.report_word_max,
            report_word_target=cfg.report_word_target,
        )

        analyst = self._get_agent()
        task_obj = Task(
            description=prompt,
            expected_output=TASK_EXPECTED_OUTPUT,
            agent=analyst,
        )

        crew = Crew(
            agents=[analyst],
            tasks=[task_obj],
            process=self._process,
            verbose=self._verbose,
            memory=self._memory,
            cache=self._cache,
            full_output=self._full_output,
            share_crew=self._share_crew,
        )

        kickoff_async = getattr(crew, "kickoff_async", None)
        if callable(kickoff_async):
            result = await kickoff_async()
        else:
            result = crew.kickoff()

        return str(result).strip()
