import { StateCard } from '@shared/ui/states/StateCard';
import { useTranslation } from 'react-i18next';

type ForbiddenStateProps = {
  title?: string;
  description?: string;
};

export function ForbiddenState({
  title,
  description,
}: ForbiddenStateProps) {
  const { t } = useTranslation();

  return (
    <StateCard
      eyebrow="states.forbidden"
      tone="warning"
      title={title ?? t('forbidden.default.title', { defaultValue: 'Forbidden' })}
      description={description ?? t('forbidden.default.description', { defaultValue: 'Your role does not have access to this route.' })}
    />
  );
}
