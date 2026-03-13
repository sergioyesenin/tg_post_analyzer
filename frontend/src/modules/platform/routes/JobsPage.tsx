import { useSession } from '@app/providers/SessionProvider';
import { JobsTableSection } from '@modules/platform/components/JobsTableSection';
import { useDeadLetterJobsQuery, useJobsFilters, useJobsRetryMutations, useJobsSummaryQuery, usePendingJobsQuery } from '@modules/platform/hooks';
import {
  deadLetterColumns,
  mapDeadLetterRows,
  mapJobsSummaryToCards,
  mapPendingJobsToRows,
  pendingJobsColumns,
} from '@modules/platform/mappers';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { canPerformAction } from '@shared/routing/policy';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function JobsPage() {
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const canRetry = canPerformAction('jobs.retry', roles);
  const { filters, applyFilters } = useJobsFilters();
  const summaryQuery = useJobsSummaryQuery();
  const pendingQuery = usePendingJobsQuery(filters);
  const deadLetterQuery = useDeadLetterJobsQuery(filters);
  const mutations = useJobsRetryMutations();

  const isLoading = summaryQuery.isLoading || pendingQuery.isLoading || deadLetterQuery.isLoading;
  const error = summaryQuery.error ?? pendingQuery.error ?? deadLetterQuery.error;

  if (isLoading) {
    return <LoadingState title="Loading jobs management" description="Fetching queue summary, pending jobs, and dead-letter rows." />;
  }

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title="Jobs module is restricted" description="Jobs visibility and retry actions are limited to admin users." />;
    }

    return <ErrorState title="Jobs module failed to load" description="One or more jobs management requests failed." />;
  }

  const summary = summaryQuery.data;
  const pending = pendingQuery.data ?? [];
  const deadLetter = deadLetterQuery.data ?? [];

  if (!summary) {
    return <EmptyState title="Jobs summary is empty" description="The jobs summary endpoint returned no payload." />;
  }

  const summaryCards = mapJobsSummaryToCards(summary, pending, deadLetter);
  const pendingRows = mapPendingJobsToRows(
    pending,
    (jobId) => {
      if (!window.confirm(`Retry failed job #${jobId}?`)) {
        return;
      }
      mutations.retryFailed.mutate(jobId);
    },
    mutations.retryFailed.variables ?? null,
  );
  const deadLetterRows = mapDeadLetterRows(
    deadLetter,
    (deadLetterId) => {
      if (!window.confirm(`Retry dead-letter row #${deadLetterId}?`)) {
        return;
      }
      mutations.retryDeadLetter.mutate(deadLetterId);
    },
    mutations.retryDeadLetter.variables ?? null,
  );

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">jobs</span>
          <h2>Jobs management</h2>
          <p>Admin-only queue inspection with confirmed retry flows for failed jobs and dead-letter rows.</p>
        </div>

        <div className="dashboard-page__meta">
          <label>
            <span>Limit</span>
            <input
              aria-label="Jobs limit"
              type="number"
              min={1}
              max={200}
              value={filters.limit}
              onChange={(event) => {
                const value = Number(event.target.value);
                applyFilters({ limit: Number.isFinite(value) && value > 0 ? value : 100 });
              }}
            />
          </label>
        </div>
      </section>

      <DashboardSummaryCards cards={summaryCards} />

      {!canRetry ? (
        <ReadOnlyNotice
          title="Retry actions are hidden for this role"
          description="Queue inspection remains visible, but retry actions require confirmed admin permissions."
          ariaLabel="Read only jobs notice"
        />
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <JobsTableSection
            title="Pending and running jobs"
            description="Queue rows from GET /api/jobs/pending."
            emptyTitle="No pending jobs"
            emptyDescription="The pending jobs endpoint returned an empty list for the current limit."
            columns={pendingJobsColumns}
            rows={
              canRetry
                ? pendingRows
                : pendingRows.map((row) => ({
                    ...row,
                    cells: {
                      ...row.cells,
                      actions: 'n/a',
                    },
                  }))
            }
          />
        </div>

        <div className="dashboard-page__secondary">
          <JobsTableSection
            title="Dead-letter queue"
            description="Rows from GET /api/jobs/dead-letter."
            emptyTitle="No dead-letter jobs"
            emptyDescription="The dead-letter endpoint returned an empty list for the current limit."
            columns={deadLetterColumns}
            rows={
              canRetry
                ? deadLetterRows
                : deadLetterRows.map((row) => ({
                    ...row,
                    cells: {
                      ...row.cells,
                      actions: 'n/a',
                    },
                  }))
            }
          />
        </div>
      </section>
    </div>
  );
}
