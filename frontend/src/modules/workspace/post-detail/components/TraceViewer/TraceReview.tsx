import { useTranslation } from 'react-i18next';
import { ReviewInfo } from '../../contracts';

export function TraceReview({ review }: { review: ReviewInfo }) {
  const { t } = useTranslation();

  return (
    <details className="detail-block trace-review" open={false}>
      <summary className="detail-block__header">
        <h4>{t('trace.review')}</h4>
        <span className="status-badge status-badge--info">
          {t('trace.iterations')}: {review.iterations}
        </span>
      </summary>
      {review.history.length > 0 && (
        <div className="trace-review__history">
          <ul>
            {review.history.map((item, idx) => (
              <li key={idx}>
                {t('trace.history_item', {
                  decision: item.decision,
                  reason: item.reason,
                  iteration: item.iteration,
                  confidence: item.confidence,
                })}
                <br />
                {t('trace.target')}: {item.target}
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}