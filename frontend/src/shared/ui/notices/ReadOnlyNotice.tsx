type ReadOnlyNoticeProps = {
  title: string;
  description: string;
  ariaLabel?: string;
};

export function ReadOnlyNotice({
  title,
  description,
  ariaLabel = 'Read only notice',
}: ReadOnlyNoticeProps) {
  return (
    <section className="dashboard-banner dashboard-banner--partial" aria-label={ariaLabel}>
      <div>
        <span className="dashboard-banner__eyebrow">read only</span>
        <strong>{title}</strong>
      </div>
      <p className="dashboard-banner__text">{description}</p>
    </section>
  );
}
