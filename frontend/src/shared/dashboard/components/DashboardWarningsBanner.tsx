import type { DashboardWarning } from '@shared/dashboard/contracts';

type DashboardWarningsBannerProps = {
  warnings: DashboardWarning[];
};

export function DashboardWarningsBanner({ warnings }: DashboardWarningsBannerProps) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <section className="dashboard-banner dashboard-banner--warning" aria-label="Dashboard warnings">
      <div>
        <span className="dashboard-banner__eyebrow">warnings</span>
        <strong>Snapshot includes non-blocking warnings</strong>
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
