import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function JobsPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="jobs"
      title={t('placeholders.jobs.title')}
      description={t('placeholders.jobs.description')}
    />
  );
}
