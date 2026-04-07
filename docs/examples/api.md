# Example: Correct API Client Usage

## Recommended reference

- `frontend/src/shared/auth/auth-api.ts`

## Why this is the preferred example

- all requests go through `shared/api/client.ts`
- auth-specific error mapping is centralized
- cookie-based refresh flow is explicit
- response payloads are converted into frontend session models immediately

## Pattern to copy

1. Define raw backend response type
2. Call `apiClient`
3. Convert to frontend DTO/model
4. Normalize roles/state before returning

## Do not copy from

- components that implicitly shape backend payloads inline
- places where feature modules call other feature APIs just for convenience
