# tg_post_analyzer

## Запуск
1. Скопируй `.env.example` в `.env` и заполни обязательные переменные.
   - Для `AUTH_JWT_SECRET` укажи криптостойкое значение (минимум 32 символа, минимум 3 класса символов).
   - Пример генерации: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Подними Postgres:

   ```bash
   docker compose up -d
   ```

3. Прогони миграции:

   ```bash
   alembic upgrade head
   ```

4. Запусти API (официальный entrypoint):

   ```bash
   uvicorn api.main:app --reload
   ```

5. Запуск парсера (отдельно от API):

   ```bash
   python main.py
   ```

## Совместимость
- `man:app` оставлен как legacy-алиас и может использоваться во временных локальных скриптах.
- Канонический путь для API и документации: `api.main:app`.
