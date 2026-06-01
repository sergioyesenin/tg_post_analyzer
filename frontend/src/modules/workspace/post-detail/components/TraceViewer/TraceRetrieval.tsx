import { useTranslation } from 'react-i18next';
import { RetrievalInfo } from '../../contracts';

export function TraceRetrieval({ retrieval }: { retrieval: RetrievalInfo }) {
  const { t } = useTranslation();

  return (
    <details className="detail-block trace-retrieval" open={false}>
      <summary className="detail-block__header">
        <h4>{t('trace.retrieval')}</h4>
        <span className="status-badge status-badge--info">
          {t('trace.retrieval_sources', { count: retrieval.sources.length })}
        </span>
      </summary>
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
      </div>
      {retrieval.sources.length > 0 && (
        <div className="trace-retrieval__sources">
          <ul>
            {retrieval.sources.map((src, idx) => (
              <li key={idx}>
                <a href={src.source} target="_blank" rel="noreferrer">
                  {src.title}
                </a>
                <span className="trace-retrieval__score">
                  {t('trace.score')}: {src.score != null ? src.score.toFixed(2) : t('trace.na')}
                </span>
                <p>{src.supports}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}