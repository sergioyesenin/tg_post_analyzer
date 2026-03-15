import { useTranslation } from 'react-i18next';

type PartialDataNoticeProps = {
  partial: boolean;
};

export function PartialDataNotice({ partial }: PartialDataNoticeProps) {
  const { t } = useTranslation();

  if (!partial) {
    return null;
  }

  return (
    <section className="dashboard-banner dashboard-banner--partial" aria-label={t('dashboard.partial.ariaLabel', { defaultValue: 'Partial data notice' })}>
      <div>
        <span className="dashboard-banner__eyebrow">{t('dashboard.partial.eyebrow', { defaultValue: 'Partial data' })}</span>
        <strong>{t('dashboard.partial.title', { defaultValue: 'Screen stays usable with partially enriched data' })}</strong>
      </div>
      <p className="dashboard-banner__text">
        {t('dashboard.partial.description', {
          defaultValue: 'This is not a hard error. Summary, filters and visible rows remain valid while optional enrichment is incomplete.',
        })}
      </p>
    </section>
  );
}
