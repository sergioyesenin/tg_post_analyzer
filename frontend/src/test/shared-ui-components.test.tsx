import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { JobStatusInline } from '@shared/ui/status/JobStatusInline';
import { MonitorStatusBadge } from '@shared/ui/status/MonitorStatusBadge';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';

describe('Shared UI components', () => {
  it('renders warnings and partial state through one shared system-alerts pattern', () => {
    render(
      <DashboardSystemAlerts
        partial
        warnings={[
          {
            code: 'events.partial',
            message: 'Some graph enrichment is incomplete.',
            severity: 'warning',
          },
        ]}
      />,
    );

    expect(screen.getByLabelText(/Системные уведомления дашборда/i)).toBeInTheDocument();
    expect(screen.getByText(/Снимок содержит неблокирующие предупреждения/i)).toBeInTheDocument();
    expect(screen.getByText(/Экран остается доступным при частично обогащенных данных/i)).toBeInTheDocument();
  });

  it('keeps shared table shells accessible by title and description', () => {
    render(
      <DashboardTableShell
        title="Accessible table"
        description="Shared table shell description."
        columns={[
          { id: 'name', label: 'Name' },
          { id: 'status', label: 'Status', align: 'right' },
        ]}
        rows={[
          {
            id: '1',
            cells: {
              name: 'Row one',
              status: 'Ready',
            },
          },
        ]}
      />,
    );

    expect(screen.getByRole('table', { name: /Accessible table/i })).toBeInTheDocument();
    expect(screen.getByText(/Shared table shell description/i)).toBeInTheDocument();
  });

  it('uses one shared read-only notice pattern across modules', () => {
    render(<ReadOnlyNotice title="Viewer access is read-only" description="Mutations stay hidden while data remains visible." />);

    expect(screen.getByLabelText(/Только чтение/i)).toBeInTheDocument();
    expect(screen.getByText(/Viewer access is read-only/i)).toBeInTheDocument();
  });

  it('normalizes report, job, and monitor statuses through shared badge metadata', () => {
    render(
      <div>
        <ReportStatusBadge status="ready" />
        <JobStatusInline status="running" jobId={42} />
        <MonitorStatusBadge status="critical" />
      </div>,
    );

    expect(screen.getByLabelText(/Статус отчета: Готов/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Задания: Выполняется/i)).toHaveTextContent('Выполняется #42');
    expect(screen.getByLabelText(/Мониторинг: Критично/i)).toBeInTheDocument();
  });
});
