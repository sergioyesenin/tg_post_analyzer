import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function UsersPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="users"
      title={t('placeholders.users.title')}
      description={t('placeholders.users.description')}
    />
  );
}
