# Example: Correct React Component Pattern

## Recommended reference

- `frontend/src/modules/workspace/posts/PostsDashboardScreen.tsx`

## Why it is the best available component example

- reads filters from a dedicated filter hook
- reads data from dedicated query hooks
- keeps API details out of JSX
- separates mapping through `mappers.tsx`
- handles loading, error, forbidden, empty, and read-only states explicitly

## What to copy

- component as orchestration + rendering shell
- remote state from hooks
- view-model generation before rendering table rows
- explicit empty/error/forbidden branches

## What not to copy literally

- the file is still too large
- prefer extracting sections if you add more UI
