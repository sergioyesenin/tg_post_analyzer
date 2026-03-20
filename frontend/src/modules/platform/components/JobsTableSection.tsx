import { OpsDataGrid } from '@modules/platform/components/OpsDataGrid';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import { EmptyState } from '@shared/ui/states/EmptyState';

type JobsTableSectionProps = {
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  eyebrowLabel: string;
  columns: DataTableColumn[];
  rows: DataTableRow[];
};

export function JobsTableSection({
  title,
  description,
  emptyTitle,
  emptyDescription,
  eyebrowLabel,
  columns,
  rows,
}: JobsTableSectionProps) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return <OpsDataGrid title={title} description={description} eyebrowLabel={eyebrowLabel} columns={columns} rows={rows} />;
}
