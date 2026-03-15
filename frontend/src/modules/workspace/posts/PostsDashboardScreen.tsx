import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import type { PostsDashboardFiltersDto } from '@shared/dashboard/contracts';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { useSession } from '@app/providers/SessionProvider';
import { usePostsDashboardQuery } from '@modules/workspace/posts/hooks';
import {
  mapPostsDashboardToViewModel,
  mapPostsRowsToTableRows,
  postsDashboardColumns,
} from '@modules/workspace/posts/mappers';

function PostsDashboardScaffold({
  children,
  filters,
  applyFilters,
  resetFilters,
}: {
  children: ReactNode;
  filters: PostsDashboardFiltersDto;
  applyFilters: (filters: PostsDashboardFiltersDto) => void;
  resetFilters: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <h2>{t('posts.dashboard.heroTitle')}</h2>
          <p>{t('posts.dashboard.sourceDescription')}</p>
        </div>
      </section>

      <DashboardFilterBar mode="posts" filters={filters} onApply={applyFilters} onReset={resetFilters} />
      {children}
    </div>
  );
}

export function PostsDashboardScreen() {
  const { t } = useTranslation();
  const { filters, applyFilters, resetFilters } = useDashboardFilters('posts');
  const { primaryRole } = useSession();
  const query = usePostsDashboardQuery(filters);

  if (query.isLoading) {
    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        <LoadingState title={t('posts.dashboard.loadingTitle')} description={t('posts.dashboard.loadingDescription')} />
      </PostsDashboardScaffold>
    );
  }

  if (query.isError) {
    const error = query.error;
    const isForbidden = error instanceof ApiError && error.status === 403;

    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        {isForbidden ? (
          <ForbiddenState title={t('posts.dashboard.forbiddenTitle')} description={t('posts.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('posts.dashboard.errorTitle')} description={t('posts.dashboard.errorDescription')} />
        )}
      </PostsDashboardScaffold>
    );
  }

  if (!query.data) {
    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        <ErrorState title={t('posts.dashboard.noDataTitle')} description={t('posts.dashboard.noDataDescription')} />
      </PostsDashboardScaffold>
    );
  }

  const viewModel = mapPostsDashboardToViewModel(query.data, primaryRole);

  return (
    <div className="dashboard-page">
      <DashboardSystemAlerts warnings={viewModel.warnings} partial={viewModel.isPartial} />

      <section className="dashboard-page__hero">
        <div>
          <h2>{t('posts.dashboard.heroTitle')}</h2>
          <p>{t('posts.dashboard.heroDescription')}</p>
        </div>
        <DashboardGeneratedAt generatedAt={viewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      <DashboardFilterBar mode="posts" filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('posts.dashboard.readOnlyTitle')} description={t('posts.dashboard.readOnlyDescription')} />
      ) : null}

      {viewModel.rows.length === 0 ? (
        <EmptyState title={t('posts.dashboard.emptyTitle')} description={t('posts.dashboard.emptyDescription')} />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--single">
          <div className="dashboard-page__primary">
            <DashboardTableShell
              title={t('posts.dashboard.tableTitle')}
              description={t('posts.dashboard.tableDescription')}
              columns={[...postsDashboardColumns]}
              rows={mapPostsRowsToTableRows(viewModel.rows)}
            />
          </div>
        </section>
      )}
    </div>
  );
}
