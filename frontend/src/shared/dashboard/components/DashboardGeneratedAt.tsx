import { useTranslation } from 'react-i18next';
import { formatUtcDateTime } from '@shared/utils/formatters';

export type DashboardGeneratedAtProps = {
  generatedAt: string;
};

export function DashboardGeneratedAt({ generatedAt }: DashboardGeneratedAtProps) {
  const { t } = useTranslation();
  const formatted = formatUtcDateTime(generatedAt);

  return (
    <div className="dashboard-generated-at" aria-label={t('dashboard.generatedAt.ariaLabel', { defaultValue: 'Dashboard generated at' })}>
      <span>{t('dashboard.generatedAt.label', { defaultValue: 'Generated at' })}</span>
      <strong>{formatted} UTC</strong>
    </div>
  );
}
