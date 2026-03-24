import { useTranslation } from 'react-i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { PartialDataNotice } from '@shared/dashboard/components/PartialDataNotice';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
import { DashboardWarningsBanner } from '@shared/dashboard/components/DashboardWarningsBanner';
import { getEventsDashboardFilterOptions, getPostsDashboardFilterOptions, getProcessesDashboardFilterOptions } from '@shared/dashboard/filter-options';
import type { DashboardFiltersByMode } from '@shared/dashboard/filters';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { buildDashboardPlaceholderResponse } from '@shared/dashboard/placeholders';
import { mapDashboardTransportToScreenViewModel } from '@shared/dashboard/view-models';

type DashboardModePageProps = {
  mode: DashboardMode;
};

export function DashboardModePage({ mode }: DashboardModePageProps) {
  const { t } = useTranslation();

  if (mode === 'posts') {
    const { filters, applyFilters, resetFilters } = useDashboardFilters('posts');
    const transport = buildDashboardPlaceholderResponse('posts', filters);
    const viewModel = mapDashboardTransportToScreenViewModel(transport);
    const filterOptions = getPostsDashboardFilterOptions({
      filters: filters as DashboardFiltersByMode['posts'],
      dashboardData: transport,
    });

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
        </section>

        <DashboardSummaryCards cards={viewModel.summaryCards} />

        <DashboardFilterBar
          mode="posts"
          filters={filters}
          options={filterOptions}
          headerSlot={<DashboardGeneratedAt generatedAt={viewModel.generatedAt} />}
          onApply={applyFilters}
          onReset={resetFilters}
        />

        <section className="dashboard-page__content">
          <div className="dashboard-page__primary">
            <AnalyticsTable
              title={viewModel.table.title}
              description={viewModel.table.description}
              columns={viewModel.table.columns}
              rows={viewModel.table.rows}
            />
          </div>

          <aside className="dashboard-page__secondary">
            <section className="dashboard-side-panel">
              <span className="state-card__eyebrow">{t('dashboard.foundation.eyebrow')}</span>
              <strong>{viewModel.secondaryPanelTitle}</strong>
              <p>{viewModel.secondaryPanelDescription}</p>
            </section>
          </aside>
        </section>
      </div>
    );
  }

  if (mode === 'events') {
    const { filters, applyFilters, resetFilters } = useDashboardFilters('events');
    const transport = buildDashboardPlaceholderResponse('events', filters);
    const viewModel = mapDashboardTransportToScreenViewModel(transport);
    const filterOptions = getEventsDashboardFilterOptions({
      filters: filters as DashboardFiltersByMode['events'],
      dashboardData: transport,
    });

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
        </section>

        <DashboardSummaryCards cards={viewModel.summaryCards} />

        <DashboardFilterBar
          mode="events"
          filters={filters}
          options={filterOptions}
          headerSlot={<DashboardGeneratedAt generatedAt={viewModel.generatedAt} />}
          onApply={applyFilters}
          onReset={resetFilters}
        />

        <section className="dashboard-page__content">
          <div className="dashboard-page__primary">
            <AnalyticsTable
              title={viewModel.table.title}
              description={viewModel.table.description}
              columns={viewModel.table.columns}
              rows={viewModel.table.rows}
            />
          </div>

          <aside className="dashboard-page__secondary">
            <section className="dashboard-side-panel">
              <span className="state-card__eyebrow">{t('dashboard.foundation.eyebrow')}</span>
              <strong>{viewModel.secondaryPanelTitle}</strong>
              <p>{viewModel.secondaryPanelDescription}</p>
            </section>
          </aside>
        </section>
      </div>
    );
  }

  const { filters, applyFilters, resetFilters } = useDashboardFilters('processes');
  const transport = buildDashboardPlaceholderResponse('processes', filters);
  const viewModel = mapDashboardTransportToScreenViewModel(transport);
  const filterOptions = getProcessesDashboardFilterOptions({
    filters: filters as DashboardFiltersByMode['processes'],
    dashboardData: transport,
  });

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
      </section>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      <DashboardFilterBar
        mode="processes"
        filters={filters}
        options={filterOptions}
        headerSlot={<DashboardGeneratedAt generatedAt={viewModel.generatedAt} />}
        onApply={applyFilters}
        onReset={resetFilters}
      />

      <section className="dashboard-page__content">
        <div className="dashboard-page__primary">
          <AnalyticsTable
            title={viewModel.table.title}
            description={viewModel.table.description}
            columns={viewModel.table.columns}
            rows={viewModel.table.rows}
          />
        </div>

        <aside className="dashboard-page__secondary">
          <section className="dashboard-side-panel">
            <span className="state-card__eyebrow">{t('dashboard.foundation.eyebrow')}</span>
            <strong>{viewModel.secondaryPanelTitle}</strong>
            <p>{viewModel.secondaryPanelDescription}</p>
          </section>
        </aside>
      </section>
    </div>
  );
}
