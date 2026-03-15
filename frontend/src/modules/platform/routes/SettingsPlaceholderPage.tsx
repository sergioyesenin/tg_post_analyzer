import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function SettingsPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="settings"
      title={t('placeholders.settings.title')}
      description={t('placeholders.settings.description')}
    />
  );
}
