import type { DashboardMode } from '@shared/dashboard/contracts';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { PartialDataNotice } from '@shared/dashboard/components/PartialDataNotice';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { DashboardWarningsBanner } from '@shared/dashboard/components/DashboardWarningsBanner';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { buildDashboardPlaceholderResponse } from '@shared/dashboard/placeholders';
import { mapDashboardTransportToScreenViewModel } from '@shared/dashboard/view-models';

type DashboardModePageProps = {
  mode: DashboardMode;
};

export function DashboardModePage({ mode }: DashboardModePageProps) {
  const { filters, applyFilters, resetFilters } = useDashboardFilters(mode);
  const transport = buildDashboardPlaceholderResponse(mode, filters);
  const viewModel = mapDashboardTransportToScreenViewModel(transport);

  return (
    <div className="dashboard-page">
      <div className="dashboard-page__system-layer">
        <DashboardWarningsBanner warnings={viewModel.warnings} />
        <PartialDataNotice partial={viewModel.isPartial} />
      </div>

      <section className="dashboard-page__hero">
        <div>
          <h2>{viewModel.title}</h2>
          <p>{viewModel.description}</p>
        </div>
        <DashboardGeneratedAt generatedAt={viewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      <DashboardFilterBar mode={mode} filters={filters} onApply={applyFilters} onReset={resetFilters} />

      <section className="dashboard-page__content">
        <div className="dashboard-page__primary">
          <DashboardTableShell
            title={viewModel.table.title}
            description={viewModel.table.description}
            columns={viewModel.table.columns}
            rows={viewModel.table.rows}
          />
        </div>

        <aside className="dashboard-page__secondary">
          <section className="dashboard-side-panel">
            <span className="state-card__eyebrow">split container foundation</span>
            <strong>{viewModel.secondaryPanelTitle}</strong>
            <p>{viewModel.secondaryPanelDescription}</p>
          </section>
        </aside>
      </section>
    </div>
  );
}
