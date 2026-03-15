import { StateCard } from '@shared/ui/states/StateCard';

type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return <StateCard eyebrow="states.empty" tone="empty" title={title} description={description} />;
}
