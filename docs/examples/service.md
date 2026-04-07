# Example: Good Service Pattern

## Recommended reference

- Frontend service/hook pattern:
  - `frontend/src/modules/workspace/post-detail/hooks.ts`
  - `frontend/src/shared/jobs/hooks.ts`

## Why this is a good example

- Query orchestration is outside the component.
- Async job actions use a reusable polling helper.
- Cache invalidation is explicit and localized.
- The component only consumes prepared query/action state.

## Pattern to copy

1. Keep API calls in `api.ts`
2. Wrap them in React Query hooks
3. Use `useAsyncJobAction` for queued backend actions
4. Invalidate only the affected query keys

## Backend service example

- `services/settings_store.py::get_setting`

Why it is useful:

- encapsulates defaults + DB override merge
- keeps callers from reimplementing settings merge rules
