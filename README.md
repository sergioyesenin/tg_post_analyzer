# tg_post_analyzer

## Запуск
1) Скопируй `.env.example` → `.env` и заполни переменные
2) Подними Postgres:

    docker compose up -d

3) Прогони миграции:

    alembic upgrade head

4) Запусти парсер/апи (пример):

    python main.py
    или
    uvicorn api.main:app --reload