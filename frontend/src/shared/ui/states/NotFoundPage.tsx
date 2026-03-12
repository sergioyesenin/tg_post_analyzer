import { ErrorState } from '@shared/ui/states/ErrorState';

export function NotFoundPage() {
  return (
    <ErrorState
      title="Route placeholder not found"
      description="The router skeleton is wired, but this route is not part of the current stage."
    />
  );
}
