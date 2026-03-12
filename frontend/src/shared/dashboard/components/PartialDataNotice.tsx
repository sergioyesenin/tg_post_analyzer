type PartialDataNoticeProps = {
  partial: boolean;
};

export function PartialDataNotice({ partial }: PartialDataNoticeProps) {
  if (!partial) {
    return null;
  }

  return (
    <section className="dashboard-banner dashboard-banner--partial" aria-label="Partial data notice">
      <div>
        <span className="dashboard-banner__eyebrow">partial snapshot</span>
        <strong>Screen stays usable with partially enriched data</strong>
      </div>
      <p className="dashboard-banner__text">
        This is not a hard error. Summary, filters and visible rows remain valid while optional enrichment is incomplete.
      </p>
    </section>
  );
}
