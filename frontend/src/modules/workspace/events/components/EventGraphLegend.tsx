import { useTranslation } from 'react-i18next';

export function EventGraphLegend() {
  const { t } = useTranslation();

  return (
    <div className="event-graph-legend" aria-label={t('events.graph.title')}>
      <span className="event-graph-legend__item"><span className="event-graph-legend__swatch event-graph-legend__swatch--root" />{t('events.graph.rootPost')}</span>
      <span className="event-graph-legend__item"><span className="event-graph-legend__swatch event-graph-legend__swatch--node" />{t('events.graph.linkedPost')}</span>
      <span className="event-graph-legend__item"><span className="event-graph-legend__swatch event-graph-legend__swatch--edge" />{t('events.graph.linkEdge')}</span>
    </div>
  );
}
