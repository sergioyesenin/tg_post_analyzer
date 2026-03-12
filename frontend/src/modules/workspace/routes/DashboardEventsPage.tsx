import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function DashboardEventsPage() {
  return (
    <RoutePlaceholder
      eyebrow="dashboard/events"
      title="Events dashboard foundation"
      description="Graph route ownership, partial data handling and detail placeholders are scaffolded without feature implementation."
      partialState={{
        partial: true,
        warnings: [
          {
            code: 'events.graph.pending',
            message: 'Graph panel implementation is intentionally deferred to the next stage.',
            severity: 'warning',
          },
        ],
      }}
    />
  );
}
