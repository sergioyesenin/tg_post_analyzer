import { useTranslation } from 'react-i18next';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function KeywordGraphPlaceholderPage() {
  const { t } = useTranslation();

  return (
    <RoutePlaceholder
      eyebrow="keyword-graph"
      title={t('placeholders.keywordGraph.title')}
      description={t('placeholders.keywordGraph.description')}
    />
  );
}
