import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RetrievalInfo } from '../../contracts';

export function TraceRetrieval({ retrieval }: { retrieval: RetrievalInfo }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const toggleExpand = () => setExpanded(!expanded);

  return (
    <div className="trace-step-card">
      <div className="trace-step-card__header" onClick={toggleExpand}>
        <div className="trace-step-card__title">
          <span className="trace-step-card__name">{t('trace.retrieval')}</span>
          <span className="status-badge status-badge--info">
            {t('trace.retrieval_sources', { count: retrieval.sources.length })}
          </span>
        </div>
        <button className="trace-step-card__expand" aria-label={expanded ? t('trace.collapse_all') : t('trace.expand_all')}>
          {expanded ? '−' : '+'}
        </button>
      </div>
      {expanded && (
        <div className="trace-step-card__content">
          <div className="trace-retrieval__grid">
            <div>
              <span>{t('trace.required')}</span> {retrieval.required ? t('trace.yes') : t('trace.no')}
            </div>
            <div>
              <span>{t('trace.used')}</span> {retrieval.used ? t('trace.yes') : t('trace.no')}
            </div>
            <div>
              <span>{t('trace.status_label')}</span> <code>{retrieval.status}</code>
            </div>
            <div>
              <span>{t('trace.decision_source')}</span> <code>{retrieval.decision_source}</code>
            </div>
            {retrieval.decision_inputs && Object.keys(retrieval.decision_inputs).length > 0 && (
              <details className="trace-retrieval__decision-inputs">
                <summary>{t('trace.decision_inputs')}</summary>
                <ul>
                  {Object.entries(retrieval.decision_inputs).map(([key, value]) => (
                    <li key={key}>
                      <strong>{key}:</strong> {String(value)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
          {retrieval.sources.length > 0 && (
            <div className="trace-retrieval__sources">
              <ul>
                {retrieval.sources.map((src, idx) => (
                <li key={idx} className="retrieval-source-item">
                  <div className="retrieval-source-header">
                    <a href={src.source} target="_blank" rel="noreferrer">
                      {src.title}
                    </a>
                    <span className="retrieval-source-domain">({src.domain})</span>
                    <span className="retrieval-source-score">Оценка: {src.score?.toFixed(2) ?? '—'}</span>
                  </div>
                  <div className="retrieval-source-metrics">
                    {src.freshness !== undefined && <span className="metric">Свежесть: {src.freshness}</span>}
                    {src.relevance !== undefined && <span className="metric">Релевантность: {src.relevance}</span>}
                    {src.content_quality !== undefined && <span className="metric">Качество: {src.content_quality}</span>}
                    {src.source_authority !== undefined && <span className="metric">Авторитет: {src.source_authority}</span>}
                    {src.semantic_relevance !== undefined && <span className="metric">Семант. рел.: {src.semantic_relevance}</span>}
                    {src.query_name && <span className="metric">Запрос: {src.query_name}</span>}
                    {src.tier && <span className="metric">Tier: {src.tier}</span>}
                  </div>
                  <p className="retrieval-source-supports">{src.supports}</p>
                </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}