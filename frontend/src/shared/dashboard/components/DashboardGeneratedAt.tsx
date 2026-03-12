export type DashboardGeneratedAtProps = {
  generatedAt: string;
};

export function DashboardGeneratedAt({ generatedAt }: DashboardGeneratedAtProps) {
  const formatted = new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(generatedAt));

  return (
    <div className="dashboard-generated-at" aria-label="Dashboard generated at">
      <span>Generated at</span>
      <strong>{formatted} UTC</strong>
    </div>
  );
}
