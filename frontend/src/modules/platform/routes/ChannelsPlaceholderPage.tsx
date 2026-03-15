import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function ChannelsPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="channels"
      title={t('placeholders.channels.title')}
      description={t('placeholders.channels.description')}
    />
  );
}
