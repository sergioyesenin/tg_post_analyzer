import { useTranslation } from 'react-i18next';

import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { getReportsPath } from '@modules/reports/filters';
import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';
import { buildReportsExportHref } from '@modules/reports/api';
import type { ReturnTypeUseGeneratePostReportsByFilterAction } from '@modules/reports/types';

type ReportsActionBarProps<TType extends ReportType> = {
  type: TType;
  filters: ReportsFiltersByType[TType];
  canGenerateBatch: boolean;
  batchAction: ReturnTypeUseGeneratePostReportsByFilterAction | null;
};

export function ReportsActionBar<TType extends ReportType>({
  type,
  filters,
  canGenerateBatch,
  batchAction,
}: ReportsActionBarProps<TType>) {
  const { t } = useTranslation();

  return (
    <>
      <section className="detail-block">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{t('states.report')}</span>
            <strong>{t('reports.actions.title', { type: t(`navigation.${type}`), defaultValue: `${type} report actions` })}</strong>
          </div>
        </div>

        <div className="detail-list">
          <div className="detail-list__item">
            <div>
              <strong>{t('reports.actions.exportTitle', { defaultValue: 'Export current list' })}</strong>
              <p>{t('reports.actions.exportDescription', { defaultValue: 'Export reuses the same URL-driven filters as the current list request.' })}</p>
            </div>
            <div className="detail-list__actions">
              <a className="table-link" href={buildReportsExportHref(type, filters, 'csv')}>
                {t('reports.actions.exportCsv', { defaultValue: 'Export CSV' })}
              </a>
              <a className="table-link" href={buildReportsExportHref(type, filters, 'json')}>
                {t('reports.actions.exportJson', { defaultValue: 'Export JSON' })}
              </a>
            </div>
          </div>

          {type === 'posts' ? (
            <div className="detail-list__item">
              <div>
                <strong>{t('reports.actions.batchTitle', { defaultValue: 'Batch generation' })}</strong>
                <p>{t('reports.actions.batchDescription', { defaultValue: 'Draft generation by current filters is available only for post reports and only for writable roles.' })}</p>
              </div>
              <div className="detail-list__actions">
                {canGenerateBatch && batchAction ? (
                  <button
                    type="button"
                    className="dashboard-button"
                    disabled={batchAction.isSubmitting || batchAction.jobStatus === 'running'}
                    onClick={() => batchAction.run(undefined)}
                  >
                    {t('reports.actions.generateByFilter', { defaultValue: 'Generate by filter' })}
                  </button>
                ) : (
                  <span className="table-link table-link--muted">{t('states.readOnly')}</span>
                )}
              </div>
            </div>
          ) : null}

          <div className="detail-list__item">
            <div>
              <strong>{t('reports.actions.routeScopeTitle', { defaultValue: 'Route scope' })}</strong>
              <p>{t('reports.actions.routeScopeDescription', { defaultValue: 'All report catalogs stay inside one route family and keep filters serializable in the URL.' })}</p>
            </div>
            <div className="detail-list__actions">
              <a className="table-link" href={getReportsPath(type)}>
                {t('reports.actions.canonicalRoute', { defaultValue: 'Canonical route' })}
              </a>
            </div>
          </div>
        </div>
      </section>

      {batchAction?.jobStatus ? (
        <AsyncActionIndicator
          title={t('reports.actions.jobTitle', { defaultValue: 'Batch report job' })}
          description={t('reports.actions.jobDescription', { defaultValue: 'Batch report generation uses the shared jobs flow and invalidates reports lists after completion.' })}
          status={batchAction.jobStatus}
          jobId={batchAction.activeJob?.job_id ?? batchAction.terminalState?.jobId}
          resultSummary={batchAction.resultSummary}
          tone={batchAction.terminalState?.status === 'failed' ? 'danger' : batchAction.jobStatus === 'done' ? 'success' : 'default'}
        />
      ) : null}
    </>
  );
}
