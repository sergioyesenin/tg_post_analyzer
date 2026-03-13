import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';

type AdminDataGridProps = {
  title: string;
  description: string;
  columns: DashboardTableColumn[];
  rows: DashboardTableRow[];
};

export function AdminDataGrid({ title, description, columns, rows }: AdminDataGridProps) {
  return <DashboardTableShell title={title} description={description} columns={columns} rows={rows} />;
}
