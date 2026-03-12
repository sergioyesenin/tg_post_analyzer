import { StateCard } from '@shared/ui/states/StateCard';

type ErrorStateProps = {
  title: string;
  description: string;
};

export function ErrorState({ title, description }: ErrorStateProps) {
  return <StateCard eyebrow="error" tone="danger" title={title} description={description} />;
}
