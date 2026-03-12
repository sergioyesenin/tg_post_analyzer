export type DashboardSummaryCard = {
  id: string;
  label: string;
  value: string;
};

type DashboardSummaryCardsProps = {
  cards: DashboardSummaryCard[];
};

export function DashboardSummaryCards({ cards }: DashboardSummaryCardsProps) {
  return (
    <section className="dashboard-summary-grid" aria-label="Dashboard summary">
      {cards.map((card) => (
        <article key={card.id} className="dashboard-summary-card">
          <span className="dashboard-summary-card__label">{card.label}</span>
          <strong className="dashboard-summary-card__value">{card.value}</strong>
        </article>
      ))}
    </section>
  );
}
