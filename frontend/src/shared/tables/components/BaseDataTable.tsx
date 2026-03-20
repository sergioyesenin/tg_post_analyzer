import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { DataGrid, type GridColDef, type GridRenderCellParams, type GridRowClassNameParams } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';

import type { DataTableColumn, DataTableRow } from '@shared/tables/types';

type BaseDataTableProps = {
  title: string;
  description: string;
  columns: DataTableColumn[];
  rows: DataTableRow[];
  variant?: 'default' | 'compact';
  eyebrowLabel: string;
  className?: string;
};

type DataGridRow = {
  id: string;
  isSelected?: boolean;
  cells: Record<string, ReactNode>;
};

export function BaseDataTable({
  title,
  description,
  columns,
  rows,
  variant = 'default',
  eyebrowLabel,
  className,
}: BaseDataTableProps) {
  const { t } = useTranslation();
  const descriptionId = `dashboard-table-description-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  const isCompact = variant === 'compact';

  const gridColumns = useMemo<GridColDef<DataGridRow>[]>(
    () =>
      columns.map((column) => ({
        field: column.id,
        headerName: column.label,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        flex: column.id === 'preview' || column.id === 'job' || column.id === 'message' ? 1.6 : 1,
        minWidth: column.id === 'actions' ? (isCompact ? 140 : 180) : column.id === 'preview' ? 260 : 140,
        align: column.align === 'right' ? 'right' : 'left',
        headerAlign: column.align === 'right' ? 'right' : 'left',
        renderCell: (params: GridRenderCellParams<DataGridRow, ReactNode>) => params.row.cells[column.id] ?? t('common.na'),
      })),
    [columns, isCompact, t],
  );

  const gridRows = useMemo<DataGridRow[]>(
    () => rows.map((row) => ({ id: row.id, isSelected: row.isSelected, cells: row.cells })),
    [rows],
  );

  return (
    <section className={['dashboard-table-shell', isCompact ? 'dashboard-table-shell--compact' : '', className].filter(Boolean).join(' ')}>
      <div className="dashboard-table-shell__header">
        <div>
          <span className="state-card__eyebrow">{eyebrowLabel}</span>
          <strong>{title}</strong>
        </div>
        <span id={descriptionId}>{description}</span>
      </div>

      <div className="dashboard-table-shell__scroll">
        <DataGrid
          aria-label={title}
          aria-describedby={descriptionId}
          className="dashboard-table-shell__grid"
          rows={gridRows}
          columns={gridColumns}
          disableRowSelectionOnClick
          disableColumnSelector
          disableDensitySelector
          disableVirtualization
          hideFooter
          autoHeight
          rowHeight={isCompact ? 56 : 72}
          columnHeaderHeight={isCompact ? 44 : 52}
          getRowClassName={(params: GridRowClassNameParams<DataGridRow>) =>
            params.row.isSelected ? 'dashboard-table-shell__row--selected' : ''
          }
          sx={{
            border: 'none',
            backgroundColor: 'transparent',
            '& .MuiDataGrid-columnHeaders': {
              backgroundColor: 'rgba(255, 250, 242, 0.85)',
              borderBottom: '1px solid var(--color-border)',
            },
            '& .MuiDataGrid-columnHeaderTitle': {
              fontWeight: 600,
            },
            '& .MuiDataGrid-cell': {
              alignItems: 'center',
              borderBottom: '1px solid var(--color-border)',
              paddingTop: isCompact ? '6px' : '10px',
              paddingBottom: isCompact ? '6px' : '10px',
            },
            '& .MuiDataGrid-row:hover': {
              backgroundColor: 'rgba(182, 73, 38, 0.05)',
            },
            '& .dashboard-table-shell__row--selected': {
              backgroundColor: 'rgba(182, 73, 38, 0.1)',
            },
          }}
        />
      </div>
    </section>
  );
}


