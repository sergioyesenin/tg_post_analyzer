import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { OpsDataGrid } from '@modules/platform/components/OpsDataGrid';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
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

    expect(screen.getByLabelText(/РЎРёСЃС‚РµРјРЅС‹Рµ СѓРІРµРґРѕРјР»РµРЅРёСЏ РґР°С€Р±РѕСЂРґР°/i)).toBeInTheDocument();
    expect(screen.getByText(/РЎРЅРёРјРѕРє СЃРѕРґРµСЂР¶РёС‚ РЅРµР±Р»РѕРєРёСЂСѓСЋС‰РёРµ РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёСЏ/i)).toBeInTheDocument();
    expect(screen.getByText(/Р­РєСЂР°РЅ РѕСЃС‚Р°РµС‚СЃСЏ РґРѕСЃС‚СѓРїРЅС‹Рј РїСЂРё С‡Р°СЃС‚РёС‡РЅРѕ РѕР±РѕРіР°С‰РµРЅРЅС‹С… РґР°РЅРЅС‹С…/i)).toBeInTheDocument();
  });

  it('renders analytics, admin, and ops tables through production-equivalent grids', () => {
    const { container } = render(
      <div>
        <AnalyticsTable
          title="Accessible analytics table"
          description="Shared analytics table description."
          columns={[
            { id: 'name', label: 'Name' },
            { id: 'status', label: 'Status', align: 'right' },
            { id: 'actions', label: 'Actions' },
          ]}
          rows={[
            {
              id: '1',
              isSelected: true,
              cells: {
                name: 'Row one',
                status: 'Ready',
                actions: <button type="button">Inspect row</button>,
              },
            },
          ]}
        />
        <AdminDataGrid
          title="Accessible admin table"
          description="Shared admin table description."
          columns={[{ id: 'user', label: 'User' }]}
          rows={[
            {
              id: '2',
              cells: {
                user: 'Admin user',
              },
            },
          ]}
        />
        <OpsDataGrid
          title="Accessible ops table"
          description="Shared ops table description."
          eyebrowLabel="ops"
          columns={[{ id: 'job', label: 'Job' }]}
          rows={[
            {
              id: '3',
              cells: {
                job: 'Retry queue',
              },
            },
          ]}
        />
      </div>,
    );

    const analyticsGrid = screen.getByRole('grid', { name: /Accessible analytics table/i });
    const adminGrid = screen.getByRole('grid', { name: /Accessible admin table/i });
    const opsGrid = screen.getByRole('grid', { name: /Accessible ops table/i });

    expect(analyticsGrid).toBeInTheDocument();
    expect(adminGrid).toBeInTheDocument();
    expect(opsGrid).toBeInTheDocument();
    expect(screen.getByText(/Shared analytics table description/i)).toBeInTheDocument();
    expect(screen.getByText(/Shared admin table description/i)).toBeInTheDocument();
    expect(screen.getByText(/Shared ops table description/i)).toBeInTheDocument();
    expect(within(analyticsGrid).getByRole('button', { name: /Inspect row/i })).toBeInTheDocument();
    expect(within(analyticsGrid).getByText(/Row one/i)).toBeInTheDocument();
    expect(within(analyticsGrid).getByText(/Ready/i)).toBeInTheDocument();
    expect(container.querySelector('.dashboard-table-shell__row--selected')).not.toBeNull();
  });

  it('uses one shared read-only notice pattern across modules', () => {
    render(<ReadOnlyNotice title="Viewer access is read-only" description="Mutations stay hidden while data remains visible." />);

    expect(screen.getByLabelText(/РўРѕР»СЊРєРѕ С‡С‚РµРЅРёРµ/i)).toBeInTheDocument();
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

    expect(screen.getByLabelText(/РЎС‚Р°С‚СѓСЃ РѕС‚С‡РµС‚Р°: Р“РѕС‚РѕРІ/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Р—Р°РґР°РЅРёСЏ: Р’С‹РїРѕР»РЅСЏРµС‚СЃСЏ/i)).toHaveTextContent('Р’С‹РїРѕР»РЅСЏРµС‚СЃСЏ #42');
    expect(screen.getByLabelText(/РњРѕРЅРёС‚РѕСЂРёРЅРі: РљСЂРёС‚РёС‡РЅРѕ/i)).toBeInTheDocument();
  });
});

