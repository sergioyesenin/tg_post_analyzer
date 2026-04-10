import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { ProcessDetailPanel } from '@modules/workspace/processes/components/ProcessDetailPanel';
import { ProcessGraphPanel } from '@modules/workspace/processes/components/ProcessGraphPanel';
import {
  useProcessDetailQueries,
  useUpdateProcessDetailReportAction,
} from '@modules/workspace/process-detail/hooks';
import { mapProcessDetailToViewModel } from '@modules/workspace/process-detail/mappers';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { QueryActivityNotice, ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function ProcessDetailsPage() {
  const { t } = useTranslation();
  const { processId: processIdParam = '' } = useParams();
  const processId = Number(processIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const canMutate = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(processId) || processId <= 0) {
    return <ErrorState title={t('processes.page.invalidTitle')} description={t('processes.page.invalidDescription')} />;
  }

  const { detailQuery, graphQuery } = useProcessDetailQueries(processId);
  const reportAction = useUpdateProcessDetailReportAction(processId);
  const hasDetailData = detailQuery.data !== undefined;
  const hasGraphData = graphQuery.data !== undefined;

  if (detailQuery.isLoading && !hasDetailData) {
    return <LoadingState title={t('processes.page.loadingTitle')} description={t('processes.page.loadingDescription')} />;
  }

  if (detailQuery.isError && !hasDetailData) {
    const error = detailQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('processes.page.forbiddenTitle')} description={t('processes.page.forbiddenDescription')} />;
    }

    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title={t('processes.page.notFoundTitle')} description={t('processes.page.notFoundDescription')} />;
    }

    return <ErrorState title={t('processes.page.errorTitle')} description={t('processes.page.errorDescription')} />;
  }

  const detail = detailQuery.data;

  if (!detail) {
    return <ErrorState title={t('processes.page.errorTitle')} description={t('processes.page.noDataDescription')} />;
  }

  const viewModel = mapProcessDetailToViewModel(detail, graphQuery.data ?? null);
  const graphPartialHint =
    graphQuery.isError || !graphQuery.data || graphQuery.data.events.length === detail.events.length
      ? null
      : t('processes.page.graphPartialHint');

  const handleBack = () => {
    if (location.key === 'default') {
      navigate('/dashboard/processes');
      return;
    }

    navigate(-1);
  };

  return (
    <div className="post-detail-page">
      <header className="post-detail-page__header">
        <div>
          <span className="state-card__eyebrow">{t('processes.page.eyebrow')}</span>
          <h1>{viewModel.process.title}</h1>
          <p>{t('processes.page.description')}</p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.process.startedAt}</span>
          <span>{t('processes.page.relatedEvents', { count: Number(viewModel.process.eventsCount) })}</span>
          <span>{t('processes.page.confirmedPosts', { count: viewModel.confirmedPostIds.length })}</span>
          <span>{t('processes.page.createdBy', { value: viewModel.process.createdBy })}</span>
          <button type="button" className="dashboard-button dashboard-button--ghost" onClick={handleBack}>
            {t('processes.page.back')}
          </button>
        </div>
      </header>

      {detailQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('processes.page.refreshingTitle', { defaultValue: 'Детали процесса обновляются' })}
          description={t('processes.page.refreshingDescription', { defaultValue: 'Текущая карточка процесса остается на экране, пока загружается обновленный payload.' })}
        />
      ) : null}

      {detailQuery.isError && hasDetailData ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('processes.page.refreshErrorTitle', { defaultValue: 'Не удалось обновить детали процесса' })}
          description={t('processes.page.refreshErrorDescription', { defaultValue: 'Показываем последнюю успешную версию деталей процесса.' })}
          tone="danger"
        />
      ) : null}

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice
          title={t('processes.page.readOnlyTitle')}
          description={t('processes.page.readOnlyDescription')}
          ariaLabel={t('processes.page.readOnlyAria')}
        />
      ) : null}

      <div className="post-detail-grid">
        <div className="post-detail-grid__main">
          <ProcessGraphPanel
            selectedTitle={viewModel.process.title}
            isLoading={graphQuery.isLoading && !hasGraphData}
            isRefreshing={graphQuery.isFetching && hasGraphData}
            isError={graphQuery.isError && !hasGraphData}
            showErrorNotice={graphQuery.isError && hasGraphData}
            viewModel={viewModel.graph}
            hasSelection
            partialHint={graphPartialHint}
            onRefresh={() => {
              void graphQuery.refetch();
            }}
          />

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('processes.page.contextEyebrow')}</span>
                <strong>{t('processes.page.contextTitle')}</strong>
              </div>
            </div>

            <div className="detail-list">
              <div className="detail-list__item">
                <div>
                  <strong>{t('processes.page.dashboardTitle')}</strong>
                  <p>{t('processes.page.dashboardDescription')}</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to="/dashboard/processes">{t('processes.page.openDashboard')}</Link>
                </div>
              </div>

              {viewModel.relatedEvents
                .filter((event) => event.postIds.length > 0)
                .slice(0, 3)
                .map((event) => (
                  <div key={event.eventId} className="detail-list__item">
                    <div>
                      <strong>{event.title}</strong>
                      <p>{t('processes.page.relatedEventDescription')}</p>
                    </div>
                    <div className="detail-list__actions">
                      <Link className="table-link" to={`/events/${event.eventId}`}>{t('processes.page.openEvent')}</Link>
                      <Link className="table-link" to={`/posts/${event.postIds[0]}`}>{t('processes.page.leadPost')}</Link>
                    </div>
                  </div>
                ))}
            </div>
          </section>
        </div>

        <aside className="post-detail-grid__side">
          <ProcessDetailPanel
            process={viewModel.process}
            graph={viewModel.graph}
            relatedEvents={viewModel.relatedEvents}
            actionSlot={
              canMutate ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                  onClick={() => reportAction.run(undefined)}
                >
                  {viewModel.process.reportStatus === 'draft' ? t('actions.updateDraftReport') : t('actions.generateDraftReport')}
                </button>
              ) : null
            }
          />

          {canMutate && reportAction.jobStatus ? (
            <AsyncActionIndicator
              title={t('processes.rows.reportJobTitle')}
              description={t('processes.rows.reportJobDescription')}
              status={reportAction.jobStatus}
              jobId={reportAction.activeJob?.job_id ?? reportAction.terminalState?.jobId}
              resultSummary={reportAction.resultSummary}
              tone={reportAction.terminalState?.status === 'failed' ? 'danger' : reportAction.jobStatus === 'done' || reportAction.jobStatus === 'completed' ? 'success' : 'default'}
            />
          ) : null}
        </aside>
      </div>
    </div>
  );
}

