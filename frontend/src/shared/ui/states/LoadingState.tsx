import { StateCard } from '@shared/ui/states/StateCard';

type LoadingStateProps = {
  title?: string;
  description?: string;
};

export function LoadingState({
  title = 'Loading workspace shell',
  description = 'Bootstrap providers and route dependencies are still resolving.',
}: LoadingStateProps) {
  return <StateCard eyebrow="loading" title={title} description={description} />;
}
