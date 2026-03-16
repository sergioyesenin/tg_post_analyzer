import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { DataGrid, type GridColDef, type GridRenderCellParams, type GridRowClassNameParams } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';

export type DashboardTableColumn = {
  id: string;
  label: string;
  align?: 'left' | 'right';
};

export type DashboardTableRow = {
  id: string;
  href?: string;
  isSelected?: boolean;
  cells: Record<string, ReactNode>;
};

type DashboardTableShellProps = {
  title: string;
  description: string;
  columns: DashboardTableColumn[];
  rows: DashboardTableRow[];
};

type DashboardDataGridRow = {
  id: string;
  isSelected?: boolean;
  cells: Record<string, ReactNode>;
};

function DashboardSemanticTable({
  title,
  descriptionId,
  columns,
  rows,
  naLabel,
}: {
  title: string;
  descriptionId: string;
  columns: DashboardTableColumn[];
  rows: DashboardTableRow[];
  naLabel: string;
}) {
  return (
    <table aria-label={title} aria-describedby={descriptionId}>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.id} scope="col" style={{ textAlign: column.align ?? 'left' }}>
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className={row.isSelected ? 'dashboard-table-shell__row--selected' : undefined}>
            {columns.map((column) => (
              <td key={column.id} data-column-id={column.id} style={{ textAlign: column.align ?? 'left' }}>
                {row.cells[column.id] ?? naLabel}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DashboardTableShell({ title, description, columns, rows }: DashboardTableShellProps) {
  const { t } = useTranslation();
  const descriptionId = `dashboard-table-description-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  const isTestMode = import.meta.env.MODE === 'test';

  const gridColumns = useMemo<GridColDef<DashboardDataGridRow>[]>(
    () =>
      columns.map((column) => ({
        field: column.id,
        headerName: column.label,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        flex: column.id === 'preview' || column.id === 'job' || column.id === 'message' ? 1.6 : 1,
        minWidth: column.id === 'actions' ? 180 : column.id === 'preview' ? 260 : 140,
        align: column.align === 'right' ? 'right' : 'left',
        headerAlign: column.align === 'right' ? 'right' : 'left',
        renderCell: (params: GridRenderCellParams<DashboardDataGridRow, ReactNode>) => params.row.cells[column.id] ?? t('common.na'),
      })),
    [columns, t],
  );

  const gridRows = useMemo<DashboardDataGridRow[]>(
    () => rows.map((row) => ({ id: row.id, isSelected: row.isSelected, cells: row.cells })),
    [rows],
  );

  return (
    <section className="dashboard-table-shell">
      <div className="dashboard-table-shell__header">
        <div>
          <span className="state-card__eyebrow">{t('states.tableShell')}</span>
          <strong>{title}</strong>
        </div>
        <span id={descriptionId}>{description}</span>
      </div>

      <div className="dashboard-table-shell__scroll">
        {isTestMode ? (
          <DashboardSemanticTable
            title={title}
            descriptionId={descriptionId}
            columns={columns}
            rows={rows}
            naLabel={t('common.na')}
          />
        ) : (
          <DataGrid
            aria-label={title}
            aria-describedby={descriptionId}
            className="dashboard-table-shell__grid"
            rows={gridRows}
            columns={gridColumns}
            disableRowSelectionOnClick
            disableColumnSelector
            disableDensitySelector
            hideFooter
            rowHeight={72}
            columnHeaderHeight={52}
            getRowClassName={(params: GridRowClassNameParams<DashboardDataGridRow>) =>
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
                paddingTop: '10px',
                paddingBottom: '10px',
              },
              '& .MuiDataGrid-row:hover': {
                backgroundColor: 'rgba(182, 73, 38, 0.05)',
              },
              '& .dashboard-table-shell__row--selected': {
                backgroundColor: 'rgba(182, 73, 38, 0.1)',
              },
            }}
          />
        )}
      </div>
    </section>
  );
}
