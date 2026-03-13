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
  return (
    <>
      <section className="detail-block">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">report actions</span>
            <strong>{type} report actions</strong>
          </div>
        </div>

        <div className="detail-list">
          <div className="detail-list__item">
            <div>
              <strong>Export current list</strong>
              <p>Export reuses the same URL-driven filters as the current list request.</p>
            </div>
            <div className="detail-list__actions">
              <a className="table-link" href={buildReportsExportHref(type, filters, 'csv')}>
                Export CSV
              </a>
              <a className="table-link" href={buildReportsExportHref(type, filters, 'json')}>
                Export JSON
              </a>
            </div>
          </div>

          {type === 'posts' ? (
            <div className="detail-list__item">
              <div>
                <strong>Batch generation</strong>
                <p>Draft generation by current filters is available only for post reports and only for writable roles.</p>
              </div>
              <div className="detail-list__actions">
                {canGenerateBatch && batchAction ? (
                  <button
                    type="button"
                    className="dashboard-button"
                    disabled={batchAction.isSubmitting || batchAction.jobStatus === 'running'}
                    onClick={() => batchAction.run(undefined)}
                  >
                    Generate by filter
                  </button>
                ) : (
                  <span className="table-link table-link--muted">Read only</span>
                )}
              </div>
            </div>
          ) : null}

          <div className="detail-list__item">
            <div>
              <strong>Route scope</strong>
              <p>All report catalogs stay inside one route family and keep filters serializable in the URL.</p>
            </div>
            <div className="detail-list__actions">
              <a className="table-link" href={getReportsPath(type)}>
                Canonical route
              </a>
            </div>
          </div>
        </div>
      </section>

      {batchAction?.jobStatus ? (
        <AsyncActionIndicator
          title="Batch report job"
          description="Batch report generation uses the shared jobs flow and invalidates reports lists after completion."
          status={batchAction.jobStatus}
          jobId={batchAction.activeJob?.job_id ?? batchAction.terminalState?.jobId}
          resultSummary={batchAction.resultSummary}
          tone={batchAction.terminalState?.status === 'failed' ? 'danger' : batchAction.jobStatus === 'done' ? 'success' : 'default'}
        />
      ) : null}
    </>
  );
}
