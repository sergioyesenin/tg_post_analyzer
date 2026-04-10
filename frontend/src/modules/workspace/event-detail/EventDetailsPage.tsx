import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { QueryActivityNotice, ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { EventDetailPanel } from '@modules/workspace/events/components/EventDetailPanel';
import { EventGraphPanel } from '@modules/workspace/events/components/EventGraphPanel';
import { useEventDetailQueries, useUpdateEventDetailReportAction } from '@modules/workspace/event-detail/hooks';
import { mapEventDetailToViewModel } from '@modules/workspace/event-detail/mappers';

export function EventDetailsPage() {
  const { t } = useTranslation();
  const { eventId: eventIdParam = '' } = useParams();
  const eventId = Number(eventIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const canMutate = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(eventId) || eventId <= 0) {
    return <ErrorState title={t('events.page.invalidTitle')} description={t('events.page.invalidDescription')} />;
  }

  const { detailQuery, graphQuery } = useEventDetailQueries(eventId);
  const reportAction = useUpdateEventDetailReportAction(eventId);
  const hasDetailData = detailQuery.data !== undefined;
  const hasGraphData = graphQuery.data !== undefined;

  if (detailQuery.isLoading && !hasDetailData) {
    return <LoadingState title={t('events.page.loadingTitle')} description={t('events.page.loadingDescription')} />;
  }

  if (detailQuery.isError && !hasDetailData) {
    const error = detailQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('events.page.forbiddenTitle')} description={t('events.page.forbiddenDescription')} />;
    }
    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title={t('events.page.notFoundTitle')} description={t('events.page.notFoundDescription')} />;
    }
    return <ErrorState title={t('events.page.errorTitle')} description={t('events.page.errorDescription')} />;
  }

  const detail = detailQuery.data;
  if (!detail) {
    return <ErrorState title={t('events.page.errorTitle')} description={t('events.page.noDataDescription')} />;
  }

  const viewModel = mapEventDetailToViewModel(detail, graphQuery.data ?? null);
  const graphPartialHint = graphQuery.isError ? null : t('events.page.graphPartialHint');

  const handleBack = () => {
    if (location.key === 'default') {
      navigate('/dashboard/events');
      return;
    }
    navigate(-1);
  };

  return (
    <div className="post-detail-page">
      <header className="post-detail-page__header">
        <div>
          <span className="state-card__eyebrow">{t('events.page.eyebrow')}</span>
          <h1>{viewModel.event.title}</h1>
          <p>{t('events.page.description')}</p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.event.startedAt}</span>
          <span>{t('events.graph.comments', { value: viewModel.event.commentsCount })}</span>
          <span>{t('events.detail.linkedPosts', { count: Number(viewModel.event.postsCount) })}</span>
          <span>{t('events.page.createdBy', { value: viewModel.event.createdBy })}</span>
          <button type="button" className="dashboard-button dashboard-button--ghost" onClick={handleBack}>{t('events.page.back')}</button>
        </div>
      </header>

      {detailQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('events.page.refreshingTitle', { defaultValue: 'Детали события обновляются' })}
          description={t('events.page.refreshingDescription', { defaultValue: 'Текущая карточка события остается на экране, пока загружается обновленный payload.' })}
        />
      ) : null}

      {detailQuery.isError && hasDetailData ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('events.page.refreshErrorTitle', { defaultValue: 'Не удалось обновить детали события' })}
          description={t('events.page.refreshErrorDescription', { defaultValue: 'Показываем последнюю успешную версию деталей события.' })}
          tone="danger"
        />
      ) : null}

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('events.page.readOnlyTitle')} description={t('events.page.readOnlyDescription')} ariaLabel={t('events.page.readOnlyAria')} />
      ) : null}

      <div className="post-detail-grid">
        <div className="post-detail-grid__main">
          <EventGraphPanel
            selectedTitle={viewModel.event.title}
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
                <span className="state-card__eyebrow">{t('events.page.contextEyebrow')}</span>
                <strong>{t('events.page.contextTitle')}</strong>
              </div>
            </div>

            <div className="detail-list">
              <div className="detail-list__item">
                <div>
                  <strong>{t('events.page.dashboardTitle')}</strong>
                  <p>{t('events.page.dashboardDescription')}</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to="/dashboard/events">{t('events.page.openDashboard')}</Link>
                </div>
              </div>

              {viewModel.event.rootPostId ? (
                <div className="detail-list__item">
                  <div>
                    <strong>{t('events.detail.rootPostTitle', { id: viewModel.event.rootPostId })}</strong>
                    <p>{t('events.page.rootPostDescription')}</p>
                  </div>
                  <div className="detail-list__actions">
                    <Link className="table-link" to={`/posts/${viewModel.event.rootPostId}`}>{t('events.page.openRootPost')}</Link>
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <aside className="post-detail-grid__side">
          <EventDetailPanel
            event={viewModel.event}
            graph={viewModel.graph}
            actionSlot={
              canMutate ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                  onClick={() => reportAction.run(undefined)}
                >
                  {viewModel.event.reportStatus === 'draft' ? t('actions.updateDraftReport') : t('actions.generateDraftReport')}
                </button>
              ) : null
            }
          />

          {canMutate && reportAction.jobStatus ? (
            <AsyncActionIndicator
              title={t('events.rows.reportJobTitle')}
              description={t('events.rows.reportJobDescription')}
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

