import { useTranslation } from 'react-i18next';

export function ProcessGraphLegend() {
  const { t } = useTranslation();

  return (
    <div className="process-graph-legend" aria-label={t('processes.graph.title')}>
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--process" />
        {t('processes.graph.processLayer')}
      </span>
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--event" />
        {t('processes.graph.nestedEvent')}
      </span>
    </div>
  );
}
