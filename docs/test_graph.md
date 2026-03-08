# Keyword Graph Test Results

## 1) Test Context
- Date: 04/03/2026
- Environment: local
- App commit/hash:
- DB size:
  - posts total:
  - posts with entities.search_lemmas:
- Feature settings (`/api/settings/effective -> features`):
    "keyword_graph_api_enabled": false,
    "keyword_graph_rollout_percent": 0

---

## 2) Search API Quality (`POST /api/keyword/search/posts`)

### 2.1 Query Set Summary
- Total queries tested: 9
- Queries with expected results: 0
- Avg took_ms: 72.22
- p50 took_ms: 63
- p95 took_ms: 188
- Max took_ms: 188
- Avg total results: 4.22
- Errors (4xx/5xx) count: 0

### 2.2 Per-query Results (top-10)
| #  | query         | filters | took_ms | total | top10_post_ids                                     | expected_post_ids | hits@10 | precision@10 | notes |
| -- | ------------- | ------- | ------- | ----- | -------------------------------------------------- | ----------------- | ------- | ------------ | ----- |
| 1  | аисты         |         | 56      | 5     | [469, 599, 518]                                    |                   | 0       | 0.0          |       |
| 2  | пожар         |         | 188     | 10    | [756, 703, 664, 637, 509, 476, 427, 288, 149, 54]  |                   | 0       | 0.0          |       |
| 3  | президент     |         | 63      | 3     | [706, 478, 528]                                    |                   | 0       | 0.0          |       |
| 4  | линия метро   |         | 79      | 2     | [685, 684]                                         |                   | 0       | 0.0          |       |
| 5  | однушка       |         | 31      | 1     | [681]                                              |                   | 0       | 0.0          |       |
| 6  | цены на жилье |         | 70      | 2     | [701, 606]                                         |                   | 0       | 0.0          |       |
| 7  | Минск-мир     |         | 0       | 0     | []                                                 |                   | 0       | 0.0          |       |
| 8  | Минск мир     |         | 44      | 5     | [90, 481, 135, 204, 91]                            |                   | 0       | 0.0          |       |
| 9  | гололедица    |         | 119     | 10    | [669, 645, 531, 495, 377, 289, 246, 382, 297, 387] |                   | 0       | 0.0          |       |


---

## 3) Graph Build Quality (`POST /api/keyword/graph/build`)

### 3.1 Summary

- Cases tested: 4
- Avg nodes: 6.5
- Avg edges: 0
- Cases marked `ok`: 0
- Cases marked `noisy`: 0
- Cases marked `missing_links`: 4
- Errors (4xx/5xx): 1


### 3.2 Per-case Results

| # | seed_post_ids | exclude_post_ids | include_neighbors/depth | nodes | edges | manual_mark (ok/noisy/missing_links) | notes |
|---|---------------|------------------|--------------------------|-------|-------|--------------------------------------|-------|
| 1 | [756,703,664,637,509,476,427,288,149] | [54] | 0 | 9 | 0 | missing_links | posts about fires, but graph has no edges |
| 2 | [669,645,531,495,377,289,246,382,297,387] | [54] | 0 | 10 | 0 | missing_links | weather/ice posts, no relationships between nodes |
| 3 | [701,606] | [] | 0 | 2 | 0 | missing_links | housing price posts, graph contains only seeds |
| 4 | [90,481,135,204,91] | [] | 0 | 5 | 0 | missing_links | Minsk-Mir posts but no links generated |
---

## 4) Graph Report Quality (`POST /api/keyword/graph/report`)

### 4.1 Summary

- Cases tested: 3
- status=ready: 3
- status=failed: 0
- status=not_found: 0
- Avg report length (chars): 1661
- Usable reports count: 0


### 4.2 Per-case Results

| # | title | post_ids | exclude_post_ids | status | content_len | manual_mark (usable/weak) | notes |
|---|-------|----------|------------------|--------|-------------|----------------------------|-------|
| 1 | string | [681] | [0] | ready | 1661 | weak | report generic and reused |
| 2 | string | [701, 606] | [0] | ready | 1661 | weak | content unrelated to housing price posts |
| 3 | string | [669,645,531,495,377,289,246,382,297,387] | [531,495,377,289,246,382,297,387] | ready | 1661 | weak | same report text reused for weather posts |
---

## 5) DB Performance Evidence

### 5.1 EXPLAIN ANALYZE (3-5 queries)
#### Query 1
- Request body:
```json
{}
