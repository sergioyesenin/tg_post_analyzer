import type { DashboardWarning } from '@shared/dashboard/contracts';
import { DashboardWarningsBanner } from '@shared/dashboard/components/DashboardWarningsBanner';
import { PartialDataNotice } from '@shared/dashboard/components/PartialDataNotice';

type DashboardSystemAlertsProps = {
  warnings: DashboardWarning[];
  partial: boolean;
};

export function DashboardSystemAlerts({ warnings, partial }: DashboardSystemAlertsProps) {
  if (!partial && warnings.length === 0) {
    return null;
  }

  return (
    <div className="dashboard-page__system-layer" aria-label="Dashboard system alerts">
      <DashboardWarningsBanner warnings={warnings} />
      <PartialDataNotice partial={partial} />
    </div>
  );
}
