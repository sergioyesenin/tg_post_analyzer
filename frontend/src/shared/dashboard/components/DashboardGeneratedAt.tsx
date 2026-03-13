import { formatUtcDateTime } from '@shared/utils/formatters';

export type DashboardGeneratedAtProps = {
  generatedAt: string;
};

export function DashboardGeneratedAt({ generatedAt }: DashboardGeneratedAtProps) {
  const formatted = formatUtcDateTime(generatedAt);

  return (
    <div className="dashboard-generated-at" aria-label="Dashboard generated at">
      <span>Generated at</span>
      <strong>{formatted} UTC</strong>
    </div>
  );
}
