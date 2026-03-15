import { useTranslation } from 'react-i18next';
import { ErrorState } from '@shared/ui/states/ErrorState';

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <ErrorState
      title={t('notFound.title', { defaultValue: 'Route placeholder not found' })}
      description={t('notFound.description', {
        defaultValue: 'The router skeleton is wired, but this route is not part of the current stage.',
      })}
    />
  );
}
