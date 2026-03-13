import { NavLink, useParams } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { canPerformAction } from '@shared/routing/policy';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { ReportsActionBar } from '@modules/reports/components/ReportsActionBar';
import { ReportsFilterBar } from '@modules/reports/components/ReportsFilterBar';
import { ReportsTableSection } from '@modules/reports/components/ReportsTableSection';
import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';
import { useGeneratePostReportsByFilterAction, useReportsFilters, useReportsListQuery } from '@modules/reports/hooks';
import { reportsCopyByType } from '@modules/reports/mappers';

function isReportType(value: string | undefined): value is ReportType {
  return value === 'posts' || value === 'events' || value === 'processes';
}

export function ReportsPage() {
  const { reportType } = useParams();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];

  if (!isReportType(reportType)) {
    return <ErrorState title="Unknown report catalog" description="The requested report route is not supported." />;
  }

  const type = reportType;
  const copy = reportsCopyByType[type];
  const { filters, applyFilters, resetFilters } = useReportsFilters(type);
  const listQuery = useReportsListQuery(type, filters);
  const canGenerateBatch = type === 'posts' && canPerformAction('reports.generate', roles);
  const postBatchFilters: ReportsFiltersByType['posts'] =
    type === 'posts'
      ? (filters as ReportsFiltersByType['posts'])
      : { channel_ids: [], categories: [], date_from: '', date_to: '', min_comments: null, limit: 100, offset: 0 };
  const postBatchAction = useGeneratePostReportsByFilterAction(postBatchFilters);
  const batchAction = type === 'posts' ? postBatchAction : null;

  if (listQuery.isLoading) {
    return <LoadingState title={`Loading ${copy.title.toLowerCase()}`} description="Fetching the selected reports catalog." />;
  }

  if (listQuery.isError) {
    const error = listQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return (
        <ForbiddenState
          title="Reports catalog is restricted"
          description="The route is visible, but the backend denied access to this reports catalog."
        />
      );
    }

    return <ErrorState title="Reports catalog failed to load" description="The reports list request failed." />;
  }

  const items = listQuery.data ?? [];

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">reports</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="dashboard-page__meta">
          <nav className="process-graph-toolbar__meta" aria-label="Report type navigation">
            <NavLink className="table-link" to="/reports/posts">
              Posts
            </NavLink>
            <NavLink className="table-link" to="/reports/events">
              Events
            </NavLink>
            <NavLink className="table-link" to="/reports/processes">
              Processes
            </NavLink>
          </nav>
        </div>
      </section>

      <ReportsFilterBar type={type} filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Read only reports notice">
          <div>
            <span className="dashboard-banner__eyebrow">read only</span>
            <strong>Viewer access keeps report catalogs readable</strong>
          </div>
          <p className="dashboard-banner__text">
            List inspection and export stay available while batch generation and other draft mutations remain hidden.
          </p>
        </section>
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <ReportsTableSection type={type} items={items} />
        </div>
        <div className="dashboard-page__secondary">
          <ReportsActionBar type={type} filters={filters} canGenerateBatch={canGenerateBatch} batchAction={batchAction} />
        </div>
      </section>
    </div>
  );
}
