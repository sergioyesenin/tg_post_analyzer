# Шаблон результатов тестирования Keyword Graph

## 1) Контекст теста
- Дата: 04/03/2026
- Окружение: local
- Commit/hash приложения:
- Размер БД:
  - всего posts:
  - posts с `entities.search_lemmas`:
  - filled_percent:
- Feature settings (`/api/settings/effective -> features`):
  - `keyword_graph_api_enabled`:
  - `keyword_graph_rollout_percent`:

---

## 2) Качество Search API (`POST /api/keyword/search/posts`)

### 2.1 Сводка по набору запросов
- Всего протестировано запросов:
- Запросов с ожидаемыми результатами:
- Средний `took_ms`:
- p50 `took_ms`:
- p95 `took_ms`:
- Максимальный `took_ms`:
- Среднее общее число результатов:
- Количество ошибок (4xx/5xx):

### 2.2 Результаты по каждому запросу (top-10)
| # | query | filters | took_ms | total | top10_post_ids | expected_post_ids | hits@10 | precision@10 | notes |
|---|-------|---------|---------|-------|----------------|-------------------|---------|--------------|-------|
| 1 |       |         |         |       |                |                   |         |              |       |

---

## 3) Качество построения графа (`POST /api/keyword/graph/build`)

### 3.1 Сводка
- Протестировано кейсов:
- Среднее число узлов:
- Среднее число ребер:
- Кейсов с оценкой `ok`:
- Кейсов с оценкой `noisy`:
- Кейсов с оценкой `missing_links`:
- Ошибок (4xx/5xx):

### 3.2 Результаты по каждому кейсу
| # | seed_post_ids | exclude_post_ids | graph_mode | include_neighbors/depth | nodes | edges | manual_mark (ok/noisy/missing_links) | notes |
|---|---------------|------------------|------------|--------------------------|-------|-------|--------------------------------------|-------|
| 1 |               |                  | transient  | true/1                   |       |       |                                      |       |

---

## 4) Качество отчетов по графу (`POST /api/keyword/graph/report`)

### 4.1 Сводка
- Протестировано кейсов:
- status=ready:
- status=failed:
- status=not_found:
- Средняя длина отчета (символов):
- Число пригодных отчетов:

### 4.2 Результаты по каждому кейсу
| # | title | post_ids | exclude_post_ids | graph_mode | status | content_len | manual_mark (usable/weak) | notes |
|---|-------|----------|------------------|------------|--------|-------------|----------------------------|-------|
| 1 |       |          |                  | transient  |        |             |                            |       |

---

## 5) Доказательства производительности БД

### 5.1 EXPLAIN ANALYZE (3-5 запросов)
#### Запрос 1
- Request body:
```json
{}
```
- Вывод EXPLAIN:
```sql
-- вставьте сюда EXPLAIN (ANALYZE, BUFFERS)
```

#### Запрос 2
- Request body:
```json
{}
```
- Вывод EXPLAIN:
```sql
-- вставьте сюда EXPLAIN (ANALYZE, BUFFERS)
```

#### Запрос 3
- Request body:
```json
{}
```
- Вывод EXPLAIN:
```sql
-- вставьте сюда EXPLAIN (ANALYZE, BUFFERS)
```

---

## 6) Ошибки и логи

### 6.1 API-ошибки (`/api/keyword/*`)
| ts | endpoint | status | message | request_id (if any) |
|----|----------|--------|---------|----------------------|

### 6.2 Stack traces
```text
вставьте stack traces
```

---

## 7) Финальная оценка
- Релевантность поиска: (good/acceptable/poor)
- Полезность графа: (good/acceptable/poor)
- Полезность отчета: (good/acceptable/poor)
- Готовность к следующему rollout step: (0/1/5/25/50/100)
- Блокирующие проблемы:
  1.
  2.
