import { StateCard } from '@shared/ui/states/StateCard';
import { useTranslation } from 'react-i18next';

type LoadingStateProps = {
  title?: string;
  description?: string;
};

export function LoadingState({
  title,
  description,
}: LoadingStateProps) {
  const { t } = useTranslation();

  return (
    <StateCard
      eyebrow="states.loading"
      title={title ?? t('loading.workspaceShell.title', { defaultValue: 'Loading workspace shell' })}
      description={description ?? t('loading.workspaceShell.description', { defaultValue: 'Bootstrap providers and route dependencies are still resolving.' })}
    />
  );
}
