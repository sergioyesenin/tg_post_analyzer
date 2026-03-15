import { useTranslation } from 'react-i18next';

type ReadOnlyNoticeProps = {
  title: string;
  description: string;
  ariaLabel?: string;
};

export function ReadOnlyNotice({
  title,
  description,
  ariaLabel = 'states.readOnly',
}: ReadOnlyNoticeProps) {
  const { t } = useTranslation();

  return (
    <section className="dashboard-banner dashboard-banner--partial" aria-label={t(ariaLabel)}>
      <div>
        <span className="dashboard-banner__eyebrow">{t('states.readOnly')}</span>
        <strong>{title}</strong>
      </div>
      <p className="dashboard-banner__text">{description}</p>
    </section>
  );
}
