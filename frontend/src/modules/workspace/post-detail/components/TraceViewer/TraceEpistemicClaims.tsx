import { useTranslation } from 'react-i18next';
import { EpistemicClaim } from '../../contracts';

export function TraceEpistemicClaims({ claims }: { claims: EpistemicClaim[] }) {
  const { t } = useTranslation();
  if (!claims.length) return null;

  return (
    <div className="detail-block trace-claims">
      <div className="detail-block__header">
        <h4>{t('trace.epistemic_claims')}</h4>
      </div>
      <ul className="trace-claims__list">
        {claims.map((claim, idx) => (
          <li key={idx}>
            <span className="status-badge status-badge--muted">
              {t(`trace.claim_type_${claim.type}`, claim.type)}
            </span>
            – {claim.text}
            <span className="trace-claims__confidence">
              ({t('trace.confidence')}: {claim.confidence})
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}