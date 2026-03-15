import { useTranslation } from 'react-i18next';

import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { useMonitorFullQuery } from '@modules/platform/hooks';
import {
  mapMonitorAlertRows,
  mapMonitorDependencyRows,
  mapMonitorOverview,
  mapMonitorSummaryCards,
  monitorAlertColumns,
  monitorDependencyColumns,
} from '@modules/platform/mappers';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function MonitorPage() {
  const { t } = useTranslation();
  const monitorQuery = useMonitorFullQuery();

  if (monitorQuery.isLoading) {
    return <LoadingState title={t('platform.monitor.loadingTitle')} description={t('platform.monitor.loadingDescription')} />;
  }

  if (monitorQuery.isError) {
    const error = monitorQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('platform.monitor.forbiddenTitle')} description={t('platform.monitor.forbiddenDescription')} />;
    }

    return <ErrorState title={t('platform.monitor.errorTitle')} description={t('platform.monitor.errorDescription')} />;
  }

  const monitor = monitorQuery.data;

  if (!monitor) {
    return <EmptyState title={t('platform.monitor.emptyTitle')} description={t('platform.monitor.emptyDescription')} />;
  }

  const summaryCards = mapMonitorSummaryCards(monitor);
  const overview = mapMonitorOverview(monitor);
  const dependencyRows = mapMonitorDependencyRows(monitor);
  const alertRows = mapMonitorAlertRows(monitor);

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.monitor')}</span>
          <h2>{t('platform.monitor.heroTitle')}</h2>
          <p>{t('platform.monitor.heroDescription')}</p>
        </div>
        <div className="dashboard-page__meta">
          <span>{t('platform.monitor.snapshotAt', { value: overview.snapshotAt })}</span>
          <span>{t('platform.monitor.timezone', { value: monitor.scheduler.timezone })}</span>
        </div>
      </section>

      <DashboardSummaryCards cards={summaryCards} />

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.statusSystem')}</span>
                <strong>{t('platform.monitor.overviewTitle')}</strong>
              </div>
            </div>

            <div className="detail-list">
              {overview.overview.map((item) => (
                <div key={item.id} className="detail-list__item">
                  <div>
                    <strong>{item.label}</strong>
                  </div>
                  <div className="detail-list__actions">{item.value}</div>
                </div>
              ))}
            </div>
          </section>

          <AdminDataGrid
            title={t('platform.monitor.dependenciesTitle')}
            description={t('platform.monitor.dependenciesDescription')}
            columns={monitorDependencyColumns}
            rows={dependencyRows}
          />
        </div>

        <div className="dashboard-page__secondary">
          {alertRows.length > 0 ? (
            <AdminDataGrid
              title={t('platform.monitor.alertsTitle')}
              description={t('platform.monitor.alertsDescription')}
              columns={monitorAlertColumns}
              rows={alertRows}
            />
          ) : (
            <EmptyState title={t('platform.monitor.noAlertsTitle')} description={t('platform.monitor.noAlertsDescription')} />
          )}

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.pipeline')}</span>
                <strong>{t('platform.monitor.runtimeTitle')}</strong>
              </div>
            </div>

            <div className="detail-list">
              <div className="detail-list__item">
                <div>
                  <strong>{t('platform.monitor.runtime.telegramTitle')}</strong>
                  <p>{t('platform.monitor.runtime.telegramDescription')}</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.runtime.telegram_pipeline.status}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>{t('platform.monitor.runtime.aiTitle')}</strong>
                  <p>{t('platform.monitor.runtime.aiDescription')}</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.runtime.ai_pipeline.status}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>{t('platform.monitor.runtime.floodRateTitle')}</strong>
                  <p>{t('platform.monitor.runtime.floodRateDescription')}</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.collect_comments.flood_rate}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>{t('platform.monitor.runtime.archiveLagTitle')}</strong>
                  <p>{t('platform.monitor.runtime.archiveLagDescription')}</p>
                </div>
                <div className="detail-list__actions">
                  {monitor.pipeline.archive.archive_lag_seconds === null ? t('common.na') : `${Math.round(monitor.pipeline.archive.archive_lag_seconds)}s`}
                </div>
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}
