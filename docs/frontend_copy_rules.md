# Frontend Copy Rules

Source of truth: `docs/frontend_handoff_checklist.md`.
Implementation source: shared i18n dictionaries and current screen behavior.
Updated: 2026-03-16.

## Principles

- User-facing copy must come from i18n resources, not ad hoc inline strings.
- Copy must describe confirmed backend behavior only.
- Partial and warning copy must never imply a hard failure if the screen remains usable.
- Forbidden copy must explain access restriction without implying missing data.
- Read-only copy must explain that data is visible but mutations are unavailable.

## Shared Copy Categories

### Loading

Use loading copy when the first snapshot is not ready yet.
Tone: neutral, short, non-diagnostic.

### Empty

Use empty copy when the request succeeds but there is no data for the current filters.
Tone: factual, should mention filters or current selection when helpful.

### Error

Use error copy when the request failed and the user can retry later.
Tone: clear and operational, without inventing unsupported troubleshooting steps.

### Forbidden

Use forbidden copy when the route or module is not available for the current role.
Tone: explicit about permission boundary.

### Partial / warnings

Use partial copy when the snapshot is usable but not fully enriched.
Tone: clear that the screen remains available.
Warnings copy should be concise and list concrete backend warnings when provided.

### Read-only

Use read-only copy when the current role can inspect data but not mutate it.
Tone: explicit about available read access and hidden/disabled mutations.

## Action Copy Rules

- Mutation buttons must use verbs tied to confirmed actions: refresh, generate, update, retry.
- Async job labels must state what background action is running or completed.
- Export links must use the exported format in the label.
- Avoid vague labels such as "Run" or "Do action".

## Field Copy Rules

- Use domain labels consistently: posts, events, processes, reports, channels, users, settings, jobs.
- Status labels must be routed through the shared status metadata layer.
- Date freshness labels must use the generated-at wording consistently on dashboard screens.

## Do Not Do

- Do not imply unsupported mutations for `viewer`.
- Do not reinterpret `partial=true` as unavailable/failed.
- Do not invent backend-only semantic states that are not present in DTOs or shared status metadata.
- Do not add emergency or destructive wording unless the backend response actually indicates it.
