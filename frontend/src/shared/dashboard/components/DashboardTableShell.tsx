import type { ReactNode } from 'react';

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

export function DashboardTableShell({ title, description, columns, rows }: DashboardTableShellProps) {
  const descriptionId = `dashboard-table-description-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

  return (
    <section className="dashboard-table-shell">
      <div className="dashboard-table-shell__header">
        <div>
          <span className="state-card__eyebrow">table shell</span>
          <strong>{title}</strong>
        </div>
        <span id={descriptionId}>{description}</span>
      </div>

      <div className="dashboard-table-shell__scroll">
        <table aria-label={title} aria-describedby={descriptionId}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  style={{ textAlign: column.align ?? 'left' }}
                >
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
                    {row.cells[column.id] ?? '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
