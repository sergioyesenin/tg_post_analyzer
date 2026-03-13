import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import { EmptyState } from '@shared/ui/states/EmptyState';

type JobsTableSectionProps = {
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  columns: DashboardTableColumn[];
  rows: DashboardTableRow[];
};

export function JobsTableSection({
  title,
  description,
  emptyTitle,
  emptyDescription,
  columns,
  rows,
}: JobsTableSectionProps) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return <AdminDataGrid title={title} description={description} columns={columns} rows={rows} />;
}
