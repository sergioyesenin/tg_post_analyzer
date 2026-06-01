import { useTranslation } from 'react-i18next';
import { useState } from 'react';

interface ExpertOutputProps {
  data: any; // llm_expert из шага
}

export function ExpertOutput({ data }: ExpertOutputProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  if (!data || typeof data !== 'object') {
    return <pre>{JSON.stringify(data, null, 2)}</pre>;
  }

  const {
    confidence,
    data_status,
    background = [],
    interpretations = [],
    consequences = [],
  } = data;

  const hasContent = background.length > 0 || interpretations.length > 0 || consequences.length > 0;

  return (
    <div className="expert-output">
      <div className="expert-output__summary">
        <div className="expert-output__status">
          <span className="expert-output__label">{t('trace.confidence')}:</span>
          <span className="expert-output__value">{confidence ?? '—'}</span>
        </div>
        <div className="expert-output__status">
          <span className="expert-output__label">{t('trace.data_status')}:</span>
          <span className={`expert-output__value expert-output__status--${data_status}`}>
            {data_status ?? t('common.na')}
          </span>
        </div>
        <div className="expert-output__counts">
          <span>{t('trace.background_count', { count: background.length })}</span>
          <span>{t('trace.interpretations_count', { count: interpretations.length })}</span>
          <span>{t('trace.consequences_count', { count: consequences.length })}</span>
        </div>
      </div>

      {hasContent && (
        <button
          className="expert-output__toggle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? t('trace.hide_details') : t('trace.show_details')}
        </button>
      )}

      {expanded && hasContent && (
        <div className="expert-output__details">
          {background.length > 0 && (
            <div className="expert-output__section">
              <h5>{t('trace.background_claims')}</h5>
              <ul>
                {background.map((item: any, idx: number) => (
                  <li key={idx}>
                    <span className="expert-output__claim-type">{item.type}</span>
                    <p>{item.text}</p>
                    <span className="expert-output__confidence">
                      {t('trace.confidence')}: {item.confidence}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {interpretations.length > 0 && (
            <div className="expert-output__section">
              <h5>{t('trace.interpretations')}</h5>
              <ul>
                {interpretations.map((item: any, idx: number) => (
                  <li key={idx}>
                    <p>{item.text}</p>
                    <span className="expert-output__confidence">
                      {t('trace.confidence')}: {item.confidence}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {consequences.length > 0 && (
            <div className="expert-output__section">
              <h5>{t('trace.consequences')}</h5>
              <ul>
                {consequences.map((item: any, idx: number) => (
                  <li key={idx}>
                    <p>{item.text}</p>
                    <span className="expert-output__confidence">
                      {t('trace.confidence')}: {item.confidence}
                    </span>
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