# Process Keyword Search Contract

## Chosen contract

Source of truth for process-to-post mapping is:

- `GET /api/dashboard/processes`
- specifically `ProcessesDashboardResponse.items[*].post_ids`

`GET /api/dashboard/processes/{process_id}/graph` is explicitly **not** the source of truth for dashboard-wide filtering.

Why this is the chosen source:

- it returns the full processes dashboard snapshot in one response
- it is the same payload the list screen already renders
- it avoids `N` graph requests for `N` visible rows
- it allows deterministic client-side filtering against matched `post_id` values from `POST /api/keyword/search/posts`

## Endpoint

- endpoint: `GET /api/dashboard/processes`
- response DTO: `ProcessesDashboardResponse`
- updated row DTO: `ProcessesDashboardItem`

## Updated DTO

Add one field to each process row:

- field: `post_ids`
- type: `number[]`
- required: yes
- nullable: no
- empty array allowed: yes

Updated row contract:

```ts
type ProcessesDashboardItemDto = {
  process_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  comments_count: number;
  involvement: number | null;
  events_count: number;
  event_ids: number[];
  post_ids: number[];
  report_status: string;
  graph_ready: boolean;
};
```

## Field semantics

`post_ids` means:

- deduplicated union of all `post_id` values linked through `EventPost` to any event listed in that row's `event_ids`
- only posts belonging to the process through its own events are included
- order is deterministic and stable for the response snapshot: ascending by first encounter under the backend's event/post loading order is acceptable, but frontend must treat the field as a set-like relation, not a ranked list
- values are unique within one row
- the field may include post ids that are not present in the current `/dashboard/posts` table, because `/dashboard/processes` and `/dashboard/posts` are different dashboard datasets with different row limits and filters
- if a process has events but none of those events has linked posts, `post_ids` is `[]`
- if a process has no events, then `event_ids` is `[]`, `post_ids` is `[]`, and `graph_ready` remains driven by graph availability rules, not by keyword search

Important clarification:

- `post_ids` is not restricted by any `/dashboard/posts` row limit
- `post_ids` is not derived from `GET /api/dashboard/processes/{process_id}/graph`
- `post_ids` is computed directly while building the `/api/dashboard/processes` snapshot

## Example response item

```json
{
  "process_id": 201,
  "title": "Policy shift cluster",
  "status": "active",
  "started_at": "2026-03-24T08:15:00Z",
  "ended_at": null,
  "confidence": 0.93,
  "comments_count": 184,
  "involvement": 4.72,
  "events_count": 3,
  "event_ids": [301, 302, 305],
  "post_ids": [9001, 9004, 9012, 9018],
  "report_status": "draft",
  "graph_ready": true
}
```

## Consistency guarantees

Guarantee:

- `event_ids` and `post_ids` in one row belong to the same `/api/dashboard/processes` snapshot

Backend rule:

- `post_ids` must be computed from the same process set and the same process-event relations used to build that response
- backend must not compute `post_ids` from a second independent per-row graph fetch
- backend must not require the client to join against `/processes/{process_id}/graph` to complete filtering

Operationally this means:

- one response is self-sufficient for dashboard-wide process filtering
- if the endpoint returns a row, its `event_ids` and `post_ids` are semantically aligned for that row
- no supported frontend flow should rely on cross-request stitching with graph payloads for list filtering

## Edge cases

Process with no posts:

- return `post_ids: []`

Process with events where some events have posts and some do not:

- return union of posts from the events that do have links
- missing links from other events do not block the row

Process with duplicated post links across multiple events:

- return each `post_id` once

Process with partially unavailable auxiliary data:

- if the main process/event/post relation can still be built, return `post_ids` from the available relation data
- keep existing top-level `partial` and `warnings` semantics for auxiliary failures

Incomplete relation state:

- if an event-to-post relation is absent in storage at snapshot time, backend returns the relation as absent; there is no placeholder or synthetic sentinel value inside `post_ids`
- partial/incomplete state is represented only through normal snapshot contents plus top-level `partial`/`warnings` when applicable, not through special values in `post_ids`

## Rollout notes

- change type: backward-compatible additive contract
- existing clients that ignore unknown fields remain unaffected
- feature flag: not required
- version bump: not required if deployed as additive extension to the current response model

Frontend availability rule:

- frontend should treat `post_ids` on `GET /api/dashboard/processes` as the contract gate
- when `items.length > 0`, the new contract is available only if every returned item includes `post_ids`
- when `items.length === 0`, there is nothing to filter, so lack of runtime proof is not blocking; rollout should be coordinated by backend deployment, not by calling `/processes/{process_id}/graph`

Explicit non-goal:

- frontend must **not** use `GET /api/dashboard/processes/{process_id}/graph` for dashboard filtering rollout detection or for dashboard-wide mapping

## Frontend rule

Client-side filtering rule for `KG-005`:

1. Call `POST /api/keyword/search/posts`
2. Build `matchedPostIds = Set<post_id>`
3. Keep a process row iff `item.post_ids` intersects `matchedPostIds`

Reference predicate:

```ts
const includeProcessRow = item.post_ids.some((postId) => matchedPostIds.has(postId));
```

## Acceptance criteria

Frontend may consider the contract approved when all statements below are true:

1. `GET /api/dashboard/processes` returns `post_ids` on every `ProcessesDashboardItemDto`.
2. `post_ids` is always an array, never `null` or omitted.
3. `post_ids` is the deduplicated union of posts linked to that process through its `event_ids`.
4. `post_ids` and `event_ids` are produced from the same dashboard snapshot.
5. `post_ids` may be `[]` for rows without linked posts.
6. Frontend does not need `GET /api/dashboard/processes/{process_id}/graph` to filter the processes table.
7. `GET /api/dashboard/processes/{process_id}/graph` remains a detail/inspection endpoint for a selected row, not a list-filtering contract.
