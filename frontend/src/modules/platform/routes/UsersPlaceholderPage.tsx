import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function UsersPlaceholderPage() {
  return (
    <RoutePlaceholder
      eyebrow="users"
      title="Users admin placeholder"
      description="The route exists to anchor RBAC, provider wiring and future admin tables."
    />
  );
}
