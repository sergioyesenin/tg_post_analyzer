# Keyword Graph Test Results

## 1) Test Context
- Date: 04/03/2026
- Environment: local
- App commit/hash:
- DB size:
  - posts total: 578
  - posts with entities.search_lemmas: 576
  - filled_percent: 99,65
- Feature settings (`/api/settings/effective -> features`):
  - keyword_graph_api_enabled: true
  - keyword_graph_rollout_percent: 100

---

## 2) Search API Quality (`POST /api/keyword/search/posts`)

### 2.1 Query Set Summary
- Total queries tested:
- Queries with expected results:
- Avg took_ms:
- p50 took_ms:
- p95 took_ms:
- Max took_ms:
- Avg total results:
- Errors (4xx/5xx) count:

### 2.2 Per-query Results (top-10)
| # | query | filters | took_ms | total | top10_post_ids | expected_post_ids | hits@10 | precision@10 | notes |
|---|-------|---------|---------|-------|----------------|-------------------|---------|--------------|-------|
| 1 |       |         |         |       |                |                   |         |              |       |

---

## 3) Graph Build Quality (`POST /api/keyword/graph/build`)

### 3.1 Summary
- Cases tested:
- Avg nodes:
- Avg edges:
- Cases marked `ok`:
- Cases marked `noisy`:
- Cases marked `missing_links`:
- Errors (4xx/5xx):

### 3.2 Per-case Results
| # | seed_post_ids | exclude_post_ids | graph_mode | include_neighbors/depth | nodes | edges | manual_mark (ok/noisy/missing_links) | notes |
|---|---------------|------------------|------------|--------------------------|-------|-------|--------------------------------------|-------|
| 1 |               |                  | transient  | true/1                   |       |       |                                      |       |

---

## 4) Graph Report Quality (`POST /api/keyword/graph/report`)

### 4.1 Summary
- Cases tested:
- status=ready:
- status=failed:
- status=not_found:
- Avg report length (chars):
- Usable reports count:

### 4.2 Per-case Results
| # | title | post_ids | exclude_post_ids | graph_mode | status | content_len | manual_mark (usable/weak) | notes |
|---|-------|----------|------------------|------------|--------|-------------|----------------------------|-------|
| 1 |       |          |                  | transient  |        |             |                            |       |

---

## 5) DB Performance Evidence

### 5.1 EXPLAIN ANALYZE (3-5 queries)
#### Query 1
- Request body:
```json
{}
```
- EXPLAIN output:
```sql
-- paste EXPLAIN (ANALYZE, BUFFERS) here
```

#### Query 2
- Request body:
```json
{}
```
- EXPLAIN output:
```sql
-- paste EXPLAIN (ANALYZE, BUFFERS) here
```

#### Query 3
- Request body:
```json
{}
```
- EXPLAIN output:
```sql
-- paste EXPLAIN (ANALYZE, BUFFERS) here
```

---

## 6) Errors and Logs

### 6.1 API errors (`/api/keyword/*`)
| ts | endpoint | status | message | request_id (if any) |
|----|----------|--------|---------|----------------------|

### 6.2 Stack traces
```text
paste stack traces
```

---

## 7) Final Assessment
- Search relevance: (good/acceptable/poor)
- Graph utility: (good/acceptable/poor)
- Report utility: (good/acceptable/poor)
- Ready for rollout step: (0/1/5/25/50/100)
- Blocking issues:
  1.
  2.
