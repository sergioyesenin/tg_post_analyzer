# Example: Good Controller / Handler Pattern

## Recommended reference

- Backend handler: `api/routers/channels.py::add_channel`

## Why this is a good example

- Router stays thin.
- Request validation uses a schema (`ChannelIn`).
- Authorization is explicit (`require_roles("admin")`).
- Heavy work is moved to a background job instead of blocking HTTP.
- Response follows the standard accepted-job contract used across the project.
- Audit logging is attached close to the user action.

## Pattern to copy

1. Validate request in `schemas/*`
2. Guard with `require_roles(...)`
3. Normalize request input
4. Deduplicate/short-circuit if needed
5. Enqueue job or call service
6. Commit once
7. Return stable response contract

## Things to avoid when copying

- do not add Telegram calls directly in the router
- do not embed large SQL blocks if a service/helper already exists
