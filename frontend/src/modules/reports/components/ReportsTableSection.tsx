import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { EmptyState } from '@shared/ui/states/EmptyState';
import type { ReportType } from '@modules/reports/contracts';
import { getReportsColumnsByType, getReportsCopyByType, mapReportsRowsToTableRows } from '@modules/reports/mappers';
import type { ReportsListResponseByType } from '@modules/reports/contracts';

type ReportsTableSectionProps<TType extends ReportType> = {
  type: TType;
  items: ReportsListResponseByType[TType];
};

export function ReportsTableSection<TType extends ReportType>({ type, items }: ReportsTableSectionProps<TType>) {
  const copy = getReportsCopyByType()[type];
  const columns = getReportsColumnsByType()[type];

  if (items.length === 0) {
    return <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />;
  }

  return (
    <DashboardTableShell
      title={copy.tableTitle}
      description={copy.description}
      columns={columns}
      rows={mapReportsRowsToTableRows(type, items)}
    />
  );
}
