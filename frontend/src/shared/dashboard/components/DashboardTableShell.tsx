import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import { BaseDataTable } from '@shared/tables/components/BaseDataTable';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';

export type DashboardTableColumn = DataTableColumn;
export type DashboardTableRow = DataTableRow;

type AnalyticsTableProps = {
  title: string;
  description: string;
  columns: readonly DashboardTableColumn[];
  rows: readonly DashboardTableRow[];
};

export const AnalyticsTable = memo(function AnalyticsTable({ title, description, columns, rows }: AnalyticsTableProps) {
  const { t } = useTranslation();

  return (
    <BaseDataTable
      title={title}
      description={description}
      columns={[...columns]}
      rows={[...rows]}
      eyebrowLabel={t('states.tableShell')}
      className="analytics-table"
    />
  );
});

export const DashboardTableShell = AnalyticsTable;


