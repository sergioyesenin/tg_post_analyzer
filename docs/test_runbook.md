# Тестовый runbook

## Уровни тестов

- `tests/`: быстрые backend-тесты на изолированных модулях, router contracts и точечном `monkeypatch`/fake-session подходе
- `tests/integration/`: реальные PostgreSQL integration-тесты против `TEST_DATABASE_URL` после применения Alembic-миграций
- `frontend/src/test/`: frontend Vitest-покрытие маршрутов, URL filters, guards и UI-поведения

## Быстрый backend-набор

Запуск основного backend-набора:

```bash
venv\Scripts\python -m pytest -q tests
```

Этот набор должен оставаться быстрым и в основном изолированным. Для него не требуется отдельная PostgreSQL test database.

## Подготовка backend integration DB

Канонический локальный setup использует PostgreSQL-контейнер из репозитория:

```bash
docker compose up -d postgres
```

Задайте `TEST_DATABASE_URL` на отдельную test database на том же сервере, например:

```bash
set TEST_DATABASE_URL=postgresql+asyncpg://tg_analytics_app:replace-with-strong-password@localhost:5432/tg_analytics_test
```

Подготовьте integration database и примените миграции:

```bash
venv\Scripts\python scripts/test_bootstrap_backend.py
```

Bootstrap-скрипт:

- гарантирует существование базы из `TEST_DATABASE_URL`
- запускает `alembic upgrade head` для этой базы

## Backend integration-набор

Запуск integration-тестов:

```bash
venv\Scripts\python -m pytest -q tests/integration --run-integration
```

Integration-тесты пропускаются, если не передан `--run-integration`. Это сохраняет default suite быстрым и защищает от случайного запуска на отсутствующей или общей базе.

## Frontend-набор

```bash
cd frontend
npm install
npm test
```

## Рекомендуемый локальный workflow

1. Запустить быстрый backend suite.
2. Запустить frontend suite.
3. Запустить backend integration suite для изменений, затрагивающих DB contracts, migrations, auth, jobs или API wiring.
