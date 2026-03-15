import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
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
    return <LoadingState title={t('platform.jobs.loadingTitle')} description={t('platform.jobs.loadingDescription')} />;
  }

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('platform.jobs.forbiddenTitle')} description={t('platform.jobs.forbiddenDescription')} />;
    }

    return <ErrorState title={t('platform.jobs.errorTitle')} description={t('platform.jobs.errorDescription')} />;
  }

  const summary = summaryQuery.data;
  const pending = pendingQuery.data ?? [];
  const deadLetter = deadLetterQuery.data ?? [];

  if (!summary) {
    return <EmptyState title={t('platform.jobs.emptyTitle')} description={t('platform.jobs.emptyDescription')} />;
  }

  const summaryCards = mapJobsSummaryToCards(summary, pending, deadLetter);
  const pendingRows = mapPendingJobsToRows(
    pending,
    (jobId) => {
      if (!window.confirm(t('platform.jobs.confirmRetryFailed', { id: jobId }))) {
        return;
      }
      mutations.retryFailed.mutate(jobId);
    },
    mutations.retryFailed.variables ?? null,
  );
  const deadLetterRows = mapDeadLetterRows(
    deadLetter,
    (deadLetterId) => {
      if (!window.confirm(t('platform.jobs.confirmRetryDeadLetter', { id: deadLetterId }))) {
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
          <span className="state-card__eyebrow">{t('states.jobs')}</span>
          <h2>{t('platform.jobs.heroTitle')}</h2>
          <p>{t('platform.jobs.heroDescription')}</p>
        </div>

        <div className="dashboard-page__meta">
          <label>
            <span>{t('fields.limit')}</span>
            <input
              aria-label={t('platform.jobs.limitAria')}
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
          title={t('platform.jobs.readOnlyTitle')}
          description={t('platform.jobs.readOnlyDescription')}
          ariaLabel={t('platform.jobs.readOnlyAria')}
        />
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <JobsTableSection
            title={t('platform.jobs.pendingTitle')}
            description={t('platform.jobs.pendingDescription')}
            emptyTitle={t('platform.jobs.pendingEmptyTitle')}
            emptyDescription={t('platform.jobs.pendingEmptyDescription')}
            columns={pendingJobsColumns}
            rows={
              canRetry
                ? pendingRows
                : pendingRows.map((row) => ({
                    ...row,
                    cells: {
                      ...row.cells,
                      actions: t('common.na'),
                    },
                  }))
            }
          />
        </div>

        <div className="dashboard-page__secondary">
          <JobsTableSection
            title={t('platform.jobs.deadLetterTitle')}
            description={t('platform.jobs.deadLetterDescription')}
            emptyTitle={t('platform.jobs.deadLetterEmptyTitle')}
            emptyDescription={t('platform.jobs.deadLetterEmptyDescription')}
            columns={deadLetterColumns}
            rows={
              canRetry
                ? deadLetterRows
                : deadLetterRows.map((row) => ({
                    ...row,
                    cells: {
                      ...row.cells,
                      actions: t('common.na'),
                    },
                  }))
            }
          />
        </div>
      </section>
    </div>
  );
}
