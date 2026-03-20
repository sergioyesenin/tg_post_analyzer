import { memo } from 'react';

import { BaseDataTable } from '@shared/tables/components/BaseDataTable';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';

type OpsDataGridProps = {
  title: string;
  description: string;
  columns: DataTableColumn[];
  rows: DataTableRow[];
  eyebrowLabel: string;
};

export const OpsDataGrid = memo(function OpsDataGrid({ title, description, columns, rows, eyebrowLabel }: OpsDataGridProps) {
  return (
    <div className="ops-data-grid">
      <BaseDataTable
        title={title}
        description={description}
        columns={columns}
        rows={rows}
        variant="compact"
        eyebrowLabel={eyebrowLabel}
        className="ops-table"
      />
    </div>
  );
});
