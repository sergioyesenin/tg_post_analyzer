# TG Post Analyzer API Contracts

Routes are mounted in `api/main.py`.

## Common Notes

- Protected endpoints use Bearer JWT via `deps.py::get_current_user`.
- Refresh session uses httpOnly cookie, not JSON body.
- CSV query arrays use `schemas/query_params.py`:
  - `channel_ids=1,2,3`
  - `categories=regional,news`
- Async actions usually return accepted-job payloads instead of final business results.

## Endpoint Catalog

### Auth

#### `POST /api/auth/login`

- Request: `schemas.auth.LoginIn`
  - `username: string`
  - `password: string`
- Response: `schemas.auth.TokenOut`
  - `access_token`
  - `refresh_token` is always `null` in current implementation
  - `token_type`
  - `expires_in_seconds`
  - `roles`

#### `POST /api/auth/refresh`

- Request: no JSON body, refresh cookie required
- Response: `schemas.auth.TokenOut`

#### `POST /api/auth/logout`

- Request: no body, requires Bearer token, optional refresh cookie
- Response:
  - `status: "ok"`
  - `refresh_revoked: boolean`

#### `GET /api/auth/me`

- Response: `schemas.auth.UserOut`

#### `GET /api/auth/users`

- Response: `list[schemas.auth.UserOut]`
- Role: `admin`

#### `POST /api/auth/users`

- Request: `schemas.auth.UserCreateIn`
  - `username`
  - `password` min 8
  - `email?`
  - `full_name?`
  - `roles: string[]`
- Response: `schemas.auth.UserOut`

#### `PUT /api/auth/users/{user_id}/roles`

- Request: `schemas.auth.UserRolesIn`
  - `roles: string[]`
- Response: `schemas.auth.UserOut`

#### `PUT /api/auth/users/{user_id}/active?active=true|false`

- Request: query param `active: bool`
- Response: `schemas.auth.UserOut`

### Channels

#### `GET /api/channels/`

- Response: `list[schemas.channel.ChannelOut]`

#### `POST /api/channels/add`

- Request: `schemas.channel.ChannelIn`
  - `username`
- Response:
  - accepted job payload:
    - `status`
    - `job_id`
    - `job_type`
    - `status_url`
    - `result_url`

#### `PATCH /api/channels/{channel_id}`

- Request: `schemas.channel.ChannelUpdate`
  - `title?`
  - `category?`
  - `is_active?`
- Response: `schemas.channel.ChannelOut`

#### `PUT /api/channels/{channel_id}/active?is_active=true|false`

- Response: `schemas.channel.ChannelOut`

#### `DELETE /api/channels/{channel_id}`

- Response:
  - `status: "deleted"`
  - `channel_id`
  - `username`

### Posts

#### `GET /api/posts/top`

- Query:
  - `date_from: datetime`
  - `date_to: datetime`
  - `limit?: int`
- Response: `list[schemas.post.PostCardOut]`

#### `GET /api/posts/{post_id}`

- Response: `schemas.post.PostDetailOut`

#### `GET /api/posts/{post_id}/comments`

- Response: `list[schemas.comment.CommentOut]`

#### `POST /api/posts/{post_id}/comments/update`

- Response: accepted job payload

### Dashboard

#### `GET /api/dashboard/posts`

- Query:
  - `date_from: datetime`
  - `date_to: datetime`
  - `limit?: 1..500`
  - `channel_ids?: CSV[int]`
  - `categories?: CSV[str]`
  - `min_comments?: int`
  - `report_status?: CSV[str]`
  - `sort_by: comments_count|date|views|involvement`
  - `sort_order: asc|desc`
- Response: `schemas.dashboard.PostsDashboardResponse`

#### `GET /api/dashboard/events`

- Query:
  - `date_from?: datetime`
  - `date_to?: datetime`
  - `limit?: 1..500`
  - `status?: CSV[str]`
  - `channel_ids?: CSV[int]`
  - `categories?: CSV[str]`
  - `min_comments?: int`
  - `sort_by: started_at|comments_count|involvement|posts_count`
  - `sort_order: asc|desc`
- Response: `schemas.dashboard.EventsDashboardResponse`

#### `GET /api/dashboard/events/{event_id}/graph`

- Response: `schemas.dashboard.EventGraphResponse`

#### `GET /api/dashboard/processes`

- Query:
  - `date_from?: datetime`
  - `date_to?: datetime`
  - `limit?: 1..500`
  - `status?: CSV[str]`
  - `min_comments?: int`
  - `sort_by: started_at|comments_count|involvement|events_count`
  - `sort_order: asc|desc`
- Response: `schemas.dashboard.ProcessesDashboardResponse`

#### `GET /api/dashboard/processes/{process_id}/graph`

- Response: `schemas.dashboard.ProcessGraphResponse`

### Linking / Events / Processes

These routes are mounted with prefix `/api`, not `/api/linking`.

#### `GET /api/events`

- Query: `limit` default 50
- Response: `list[schemas.linking.EventSummaryOut]`

#### `POST /api/linking/run?post_id=<id>`

- Response: `schemas.linking.JobAcceptedResponse`

#### `POST /api/events/rebuild`

- Query:
  - `date_from: datetime`
  - `date_to: datetime`
- Response: `schemas.linking.JobAcceptedResponse`

#### `POST /api/processes/rebuild`

- Query:
  - `date_from: datetime`
  - `date_to: datetime`
- Response: `schemas.linking.JobAcceptedResponse`

#### `GET /api/posts/{post_id}/links`

- Response: `schemas.linking.PostLinksResponse`

#### `GET /api/events/{event_id}`

- Response: `schemas.linking.EventDetailOut`

#### `GET /api/processes/{process_id}`

- Response: `schemas.linking.ProcessDetailOut`

### Reports

#### `GET /api/reports/post/{post_id}`

- Response: `schemas.report.ReportOut`

#### `POST /api/reports/post/{post_id}/update`

- Response: accepted job payload

#### `GET /api/reports/posts/list`

- Query:
  - `channel_ids?: CSV[int]`
  - `categories?: CSV[str]`
  - `date_from?`
  - `date_to?`
  - `limit`
  - `offset`
- Response:
  - array of plain dicts
  - shape:
    - `report_id`
    - `post_id`
    - `status`
    - `created_at`
    - `post_date`
    - `channel_id`
    - `channel_username`
    - `channel_category`

#### `GET /api/reports/posts/export`

- Query: same filters + `format=json|csv`
- JSON response:
  - `total`
  - `items[]` with report/post/channel fields
- CSV response: same columns

#### `GET /api/reports/events/list`

- Query:
  - `event_id?`
  - `date_from?`
  - `date_to?`
  - `limit`
  - `offset`
- Response: plain dict array with:
  - `report_id`
  - `event_id`
  - `event_title`
  - `status`
  - `version`
  - `created_at`

#### `GET /api/reports/events/export`

- Query: same + `format=json|csv`
- Response: JSON or CSV with `report_text`

#### `GET /api/reports/processes/list`

- Query:
  - `process_id?`
  - `date_from?`
  - `date_to?`
  - `limit`
  - `offset`
- Response: plain dict array with:
  - `report_id`
  - `process_id`
  - `process_title`
  - `status`
  - `version`
  - `created_at`

#### `GET /api/reports/processes/export`

- Query: same + `format=json|csv`

#### `POST /api/reports/posts/generate-by-filter`

- Query:
  - `channel_ids?: CSV[int]`
  - `categories?: CSV[str]`
  - `date_from?`
  - `date_to?`
  - `min_comments?`
  - `limit`
- Response:
  - accepted batch job payload
  - includes nested `batch` echo of filters

#### `POST /api/reports/events/{event_id}/update`

- Response: accepted job payload

#### `POST /api/reports/processes/{process_id}/update`

- Response: accepted job payload

### Settings

#### `GET /api/settings/`

- Response: `list[schemas.settings.AppSettingOut]`
- Internal keys starting with `runtime.` are filtered out

#### `GET /api/settings/effective`

- Response: merged effective settings object
- Includes defaults plus DB overrides

#### `PUT /api/settings/{key}`

- Request: `schemas.settings.AppSettingUpdateIn`
  - `value_json: dict`
  - `description?`
- Response: `schemas.settings.AppSettingOut`

### Jobs

#### `GET /api/jobs/summary`

- Response:
  - `total`
  - `by_status`

#### `GET /api/jobs/pending`

- Query: `limit`
- Response: array of simplified job dicts

#### `GET /api/jobs/dead-letter`

- Query: `limit`
- Response: array of dead-letter dicts

#### `POST /api/jobs/dead-letter/{dead_letter_id}/retry`

- Response:
  - `status`
  - `dead_letter_id`
  - `source_job_id`
  - `new_job_id`
  - `type`

#### `POST /api/jobs/failed/{job_id}/retry`

- Response:
  - `status`
  - `job_id`
  - `type`

#### `POST /api/jobs/archive/run`

- Query:
  - `retention_days`
  - `batch_limit`
- Response: queue confirmation payload

#### `POST /api/jobs/retention/run`

- Query:
  - `done_retention_days`
  - `dead_letter_retention_days`
  - `batch_limit`
- Response: queue confirmation payload

#### `GET /api/jobs/{job_id}`

- Response: serialized job status object

#### `GET /api/jobs/{job_id}/result`

- Response:
  - final result dict if job `done`
  - failure dict if job `failed`
  - or `{ status, job_id, ready: false, result: null }`

### Monitor

All monitor routes require `admin`.

- `GET /api/monitor/summary`
- `GET /api/monitor/db-size`
- `GET /api/monitor/health`
- `GET /api/monitor/system`
- `GET /api/monitor/jobs`
- `GET /api/monitor/full`
- `GET /api/monitor/scheduler`
- `GET /api/monitor/alerts`
- `GET /api/monitor/runtime-topology`
- `GET /api/monitor/pipeline`

Responses are plain dict snapshots from `services.monitoring.py`.

### Keyword Graph

#### `POST /api/keyword/search/posts`

- Request: `schemas.keyword_graph.KeywordSearchRequest`
  - `query`
  - `limit`
  - `date_from?`
  - `date_to?`
  - `channel_ids[]`
- Response: `schemas.keyword_graph.KeywordSearchResponse`

#### `POST /api/keyword/graph/build`

- Request: `schemas.keyword_graph.GraphBuildRequest`
  - `post_ids[]`
  - `exclude_post_ids[]`
  - `graph_mode`
  - `include_neighbors`
  - `neighbor_depth`
  - `neighbor_limit`
  - `allowed_link_types[]`
  - `min_shared_lemmas`
  - `max_time_distance_hours`
  - `min_text_similarity`
  - transient limits/timeouts
- Response: `schemas.keyword_graph.GraphBuildResponse`

#### `POST /api/keyword/graph/report`

- Request: `schemas.keyword_graph.GraphReportRequest`
  - same graph parameters
  - optional `title`
- Response: `schemas.keyword_graph.GraphReportResponse`
  - `status`
  - `title`
  - `post_ids`
  - `excluded_post_ids`
  - `content`

## Internal Contracts

### Core persistence entities

- Auth: `User`, `Role`, `UserRole`, `AuthIdentity`, `AuthRefreshToken`, `AuthRateLimitBucket`, `AuditLog`
- Config/runtime: `AppSetting`
- Content: `Channel`, `Post`, `Comment`, `Report`, `PostFact`
- Queue: `Job`, `JobDeadLetter`
- Graph/domain: `PostLink`, `Event`, `EventPost`, `Process`, `ProcessEvent`, `EventReport`, `ProcessReport`
- Archive: `Archive*` tables

### Important enums

- `VerificationStatus`: `proposed | verified | rejected | needs_review`
- `LinkDirection`: `src_to_dst | dst_to_src | none`
- `PostLinkType`: `same_event | update | contradiction | cause | consequence | background | related | unrelated`
- `ProcessRelationType`: `cause | effect | update | contradiction | related`

### Job contract conventions

Common payload fields seen across jobs:

- `source`
- `requested_by_user_id`
- entity id like `post_id`, `event_id`, `process_id`
- for rebuild jobs: `date_from`, `date_to`
- batch jobs: nested `filters`

Result payloads are ad hoc and stored in `jobs.payload_json["_job_result"]`.
This is a real contract even though it is not formalized.

## External Integrations

### Telegram / Telethon

- Used by:
  - ingestion
  - add channel
  - comments refresh
- Main code:
  - `client/telegram.py`
  - `services/ingestion_core.py`
  - `services/TGqueries.py`

### AI report generator

- Used by:
  - `services/reporting.py`
  - `api/routers/keyword_graph.py`
- Contract style:
  - report payload dicts validated/consumed through `schemas/report.py`

### Embeddings endpoint

- Used by: `services/linking/embeddings.py`
- Current role: assist linking retrieval/ranking
