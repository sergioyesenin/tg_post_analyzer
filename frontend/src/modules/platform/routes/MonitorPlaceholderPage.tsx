import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function MonitorPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="monitor"
      title={t('placeholders.monitor.title')}
      description={t('placeholders.monitor.description')}
    />
  );
}
