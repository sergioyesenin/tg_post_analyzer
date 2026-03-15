import { useTranslation } from 'react-i18next';
import type { DashboardWarning } from '@shared/dashboard/contracts';

type DashboardWarningsBannerProps = {
  warnings: DashboardWarning[];
};

export function DashboardWarningsBanner({ warnings }: DashboardWarningsBannerProps) {
  const { t } = useTranslation();

  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="dashboard-banner dashboard-banner--warning" aria-label={t('dashboard.warnings.ariaLabel', { defaultValue: 'Dashboard warnings' })}>
      <div>
        <span className="dashboard-banner__eyebrow">{t('dashboard.warnings.eyebrow', { defaultValue: 'Warnings' })}</span>
        <strong>{t('dashboard.warnings.title', { defaultValue: 'Snapshot includes non-blocking warnings' })}</strong>
      </div>
      <ul className="dashboard-banner__list">
        {warnings.map((warning) => (
          <li key={warning.code}>
            <strong>{warning.severity}</strong>
            <span>{warning.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
