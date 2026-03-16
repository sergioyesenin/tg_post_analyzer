import { useTranslation } from 'react-i18next';

type ProcessGraphToolbarProps = {
  title: string;
  eventCount: number;
  postCount: number;
  isLoading: boolean;
  onRefresh: () => void;
  onResetView?: () => void;
};

export function ProcessGraphToolbar({
  title,
  eventCount,
  postCount,
  isLoading,
  onRefresh,
  onResetView,
}: ProcessGraphToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className="process-graph-toolbar">
      <div>
        <span className="state-card__eyebrow">{t('processes.graph.toolbarEyebrow')}</span>
        <strong>{title}</strong>
      </div>
      <div className="process-graph-toolbar__meta">
        <span>{t('processes.graph.eventsMeta', { value: eventCount })}</span>
        <span>{t('processes.graph.postsMeta', { value: postCount })}</span>
        {onResetView ? (
          <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onResetView} disabled={isLoading}>
            {t('actions.reset')}
          </button>
        ) : null}
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          {t('processes.graph.reload')}
        </button>
      </div>
    </div>
  );
}
