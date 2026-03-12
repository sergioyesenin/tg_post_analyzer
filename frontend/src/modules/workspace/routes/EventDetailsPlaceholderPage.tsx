import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function EventDetailsPlaceholderPage() {
  return (
    <RoutePlaceholder
      eyebrow="events/:eventId"
      title="Event details placeholder"
      description="The route is reserved for the future graph-aware event details workflow."
    />
  );
}
