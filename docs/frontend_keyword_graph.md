# Руководство по интеграции UI для Keyword Graph

## Feature flag

- Ключ: `features.keyword_graph_api_enabled`
- Включается через admin settings API:
  - `PUT /api/settings/features`
  - body: `{"value_json":{"keyword_graph_api_enabled": true, "keyword_graph_rollout_percent": 100}}`

## API-контракты

### 1) Поиск постов по ключевому слову или фразе

- Endpoint: `POST /api/keyword/search/posts`
- Роли: `admin`, `analyst`
- Request:
```json
{
  "query": "повышение ставки",
  "limit": 50,
  "date_from": "2026-03-01T00:00:00Z",
  "date_to": "2026-03-04T23:59:59Z",
  "channel_ids": [1, 2]
}
```
- Поля ответа для рендера списка:
  - `items[].post_id`
  - `items[].channel_username`
  - `items[].date`
  - `items[].text_preview`
  - `items[].comments_count`, `items[].views`, `items[].involvement`
  - `items[].rank`, `items[].matched_lemmas`

### 2) Построение графа из выбранных постов с исключениями

- Endpoint: `POST /api/keyword/graph/build`
- Роли: `admin`, `analyst`
- Request:
```json
{
  "post_ids": [101, 102, 103],
  "exclude_post_ids": [102],
  "graph_mode": "transient",
  "include_neighbors": true,
  "neighbor_depth": 1,
  "neighbor_limit": 400,
  "allowed_link_types": [],
  "min_shared_lemmas": 2,
  "max_time_distance_hours": 96,
  "min_text_similarity": 0.2
}
```
- Response:
  - `nodes[]`: карточки постов для узлов графа
  - `edges[]`: связи для ребер графа
  - `edges[].edge_source`: `transient` или `persisted`
  - `edges[].evidence`: объяснение, почему ребро существует в transient mode

Примечания:

- `graph_mode="transient"` — режим по умолчанию и рекомендуемый режим для сессий keyword-analysis.
- Transient mode не записывает links в БД.

### 3) Генерация AI-отчета по графу

- Endpoint: `POST /api/keyword/graph/report`
- Роли: `admin`, `analyst`
- Request:
```json
{
  "title": "Граф по теме ставок",
  "post_ids": [101, 103, 109],
  "exclude_post_ids": [109],
  "graph_mode": "transient",
  "include_neighbors": true,
  "neighbor_depth": 1,
  "neighbor_limit": 400,
  "allowed_link_types": [],
  "min_shared_lemmas": 2,
  "max_time_distance_hours": 96,
  "min_text_similarity": 0.2
}
```
- Response:
  - `status`: `ready|failed|not_found`
  - `content`: markdown/plain text с телом отчета

## UI-flow

1. Search panel:
   - input `query`, опциональные фильтры по дате и каналу, кнопка `Найти`
   - рендер таблицы/списка с checkbox у каждого поста
2. Selection panel:
   - показать выбранные посты
   - дать toggle `exclude` для каждого выбранного поста
3. Graph panel:
   - вызвать `/graph/build` с выбранными и исключенными id
   - рендерить:
     - label узла: `text_preview` + `@channel_username`
     - label ребра: `link_type`, опционально `score`
4. Report panel:
   - кнопка `Сгенерировать отчет`
   - вызвать `/graph/report`
   - отрендерить `content`, добавить copy/export controls

## UX-примечания

- Debounce для search input: `300-500 ms`, но сам запрос выполнять только по явному submit.
- Для повторяющихся запросов кэшировать в frontend state по ключу `query+filters`.
- Показывать server latency через `took_ms` из search response.
- При выключенной feature: если сервер вернул `404 Feature disabled`, скрывать страницу и показывать admin-only banner.
