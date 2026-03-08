# Keyword Graph UI Integration Guide

## Feature Flag
- Key: `features.keyword_graph_api_enabled`
- Enable via admin settings API:
  - `PUT /api/settings/features`
  - body: `{"value_json":{"keyword_graph_api_enabled": true, "keyword_graph_rollout_percent": 100}}`

## API Contracts

### 1) Search posts by keyword or phrase
- Endpoint: `POST /api/keyword/search/posts`
- Roles: `admin`, `analyst`
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
- Response fields for list rendering:
  - `items[].post_id`
  - `items[].channel_username`
  - `items[].date`
  - `items[].text_preview`
  - `items[].comments_count`, `items[].views`, `items[].involvement`
  - `items[].rank`, `items[].matched_lemmas`

### 2) Build graph from selected posts (+ exclusions)
- Endpoint: `POST /api/keyword/graph/build`
- Roles: `admin`, `analyst`
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
  - `nodes[]`: post cards for graph nodes.
  - `edges[]`: links for graph edges.
  - `edges[].edge_source`: `transient` or `persisted`.
  - `edges[].evidence`: why edge exists (for transient mode).

Notes:
- `graph_mode="transient"` is default and recommended for keyword analysis sessions.
- Transient mode does not write links into DB.

### 3) Generate AI report for graph
- Endpoint: `POST /api/keyword/graph/report`
- Roles: `admin`, `analyst`
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
  - `content`: markdown/plain text report body.

## UI Flow (recommended)
1. Search panel:
   - input `query`, optional date/channel filters, button `Найти`.
   - render table/list with checkbox per post.
2. Selection panel:
   - show selected posts.
   - allow `exclude` toggle per selected post.
3. Graph panel:
   - call `/graph/build` with selected/excluded ids.
   - render:
     - node label: `text_preview` + `@channel_username`.
     - edge label: `link_type`, optional `score`.
4. Report panel:
   - button `Сгенерировать отчёт`.
   - call `/graph/report`.
   - render `content`, add copy/export controls.

## UX Notes
- Debounce search input (300-500 ms) but execute request only on explicit submit.
- For repeat queries, cache by key `query+filters` in frontend state.
- Show server latency using `took_ms` from search response.
- Graceful feature-off handling: if `404 Feature disabled`, hide page and show admin-only banner.
