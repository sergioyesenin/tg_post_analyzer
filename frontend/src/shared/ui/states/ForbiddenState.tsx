import { StateCard } from '@shared/ui/states/StateCard';

type ForbiddenStateProps = {
  title?: string;
  description?: string;
};

export function ForbiddenState({
  title = 'Forbidden',
  description = 'Your role does not have access to this route.',
}: ForbiddenStateProps) {
  return <StateCard eyebrow="forbidden" tone="warning" title={title} description={description} />;
}
