import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function ProcessDetailsPlaceholderPage() {
  return (
    <RoutePlaceholder
      eyebrow="processes/:processId"
      title="Process details placeholder"
      description="The route is reserved for the future process graph and event linkage workflow."
    />
  );
}
