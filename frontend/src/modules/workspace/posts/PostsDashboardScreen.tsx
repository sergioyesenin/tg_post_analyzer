import type { ReactNode } from 'react';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { PartialDataNotice } from '@shared/dashboard/components/PartialDataNotice';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { DashboardWarningsBanner } from '@shared/dashboard/components/DashboardWarningsBanner';
import type { PostsDashboardFiltersDto } from '@shared/dashboard/contracts';
import { useDashboardFilters } from '@shared/dashboard/hooks';
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
  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <h2>Posts workspace</h2>
          <p>Primary source: `/api/dashboard/posts`. Filters stay URL-owned and route-local.</p>
        </div>
      </section>

      <DashboardFilterBar mode="posts" filters={filters} onApply={applyFilters} onReset={resetFilters} />
      {children}
    </div>
  );
}

export function PostsDashboardScreen() {
  const { filters, applyFilters, resetFilters } = useDashboardFilters('posts');
  const { primaryRole } = useSession();
  const query = usePostsDashboardQuery(filters);

  if (query.isLoading) {
    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        <LoadingState
          title="Loading posts dashboard"
          description="The dashboard snapshot is being loaded from /api/dashboard/posts."
        />
      </PostsDashboardScaffold>
    );
  }

  if (query.isError) {
    const error = query.error;
    const isForbidden = error instanceof ApiError && error.status === 403;

    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        {isForbidden ? (
          <ForbiddenState
            title="Posts dashboard is not available for this role"
            description="The route is visible, but the backend denied access to the posts dashboard snapshot."
          />
        ) : (
          <ErrorState
            title="Posts dashboard failed to load"
            description="The snapshot request failed. Adjust filters or retry when the backend becomes available."
          />
        )}
      </PostsDashboardScaffold>
    );
  }

  if (!query.data) {
    return (
      <PostsDashboardScaffold filters={filters} applyFilters={applyFilters} resetFilters={resetFilters}>
        <ErrorState
          title="Posts dashboard returned no data"
          description="The request finished without a dashboard payload. Retry when the backend snapshot is available."
        />
      </PostsDashboardScaffold>
    );
  }

  const viewModel = mapPostsDashboardToViewModel(query.data, primaryRole);

  return (
    <div className="dashboard-page">
      <div className="dashboard-page__system-layer">
        <DashboardWarningsBanner warnings={viewModel.warnings} />
        <PartialDataNotice partial={viewModel.isPartial} />
      </div>

      <section className="dashboard-page__hero">
        <div>
          <h2>Posts workspace</h2>
          <p>Snapshot-driven analysis of top posts with detail entry points and report status visibility.</p>
        </div>
        <DashboardGeneratedAt generatedAt={viewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      <DashboardFilterBar mode="posts" filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Read only notice">
          <div>
            <span className="dashboard-banner__eyebrow">read only</span>
            <strong>Viewer access hides mutation entry points</strong>
          </div>
          <p className="dashboard-banner__text">
            Open-post navigation stays available, while comments update and report update entry points remain hidden.
          </p>
        </section>
      ) : null}

      {viewModel.rows.length === 0 ? (
        <EmptyState
          title="No posts match the current filters"
          description="The dashboard loaded successfully, but the snapshot contains no post rows for these filters."
        />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--single">
          <div className="dashboard-page__primary">
            <DashboardTableShell
              title="Posts table"
              description="Dense list from /api/dashboard/posts items with detail entry points and report status badges."
              columns={[...postsDashboardColumns]}
              rows={mapPostsRowsToTableRows(viewModel.rows)}
            />
          </div>
        </section>
      )}
    </div>
  );
}
