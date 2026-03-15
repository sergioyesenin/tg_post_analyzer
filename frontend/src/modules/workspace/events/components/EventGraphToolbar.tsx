import { useTranslation } from 'react-i18next';

type EventGraphToolbarProps = {
  title: string;
  nodeCount: number;
  edgeCount: number;
  isLoading: boolean;
  onRefresh: () => void;
};

export function EventGraphToolbar({ title, nodeCount, edgeCount, isLoading, onRefresh }: EventGraphToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className="event-graph-toolbar">
      <div>
        <span className="state-card__eyebrow">{t('events.graph.toolbarEyebrow')}</span>
        <strong>{title}</strong>
      </div>
      <div className="event-graph-toolbar__meta">
        <span>{t('events.graph.nodes', { value: nodeCount })}</span>
        <span>{t('events.graph.edges', { value: edgeCount })}</span>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          {t('events.graph.reload')}
        </button>
      </div>
    </div>
  );
}
