import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function ReportsPlaceholderPage() {
  const { t } = useTranslation();
  const { reportType = 'unknown' } = useParams();

  return (
    <RoutePlaceholder
      eyebrow={`reports/${reportType}`}
      title={t('placeholders.reports.title')}
      description={t('placeholders.reports.description')}
    />
  );
}
