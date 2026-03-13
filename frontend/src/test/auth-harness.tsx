import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { QueryClientProvider } from '@app/providers/QueryClientProvider';
import { SessionProvider } from '@app/providers/SessionProvider';
import { ThemeProvider } from '@app/providers/ThemeProvider';
import { AuthGuard } from '@app/router/guards/AuthGuard';
import { RoleGuard } from '@app/router/guards/RoleGuard';
import { AppShell } from '@app/shell/AppShell';
import { ChannelsPage } from '@modules/admin/routes/ChannelsPage';
import { SettingsPage } from '@modules/admin/routes/SettingsPage';
import { UsersPage } from '@modules/admin/routes/UsersPage';
import { LoginPage } from '@modules/auth/routes/LoginPage';
import { JobsPage } from '@modules/platform/routes/JobsPage';
import { MonitorPage } from '@modules/platform/routes/MonitorPage';
import { KeywordGraphPage } from '@modules/keyword-graph/KeywordGraphPage';
import { EventDetailsPage } from '@modules/workspace/event-detail/EventDetailsPage';
import { PostDetailsPage } from '@modules/workspace/post-detail/PostDetailsPage';
import { ProcessDetailsPage } from '@modules/workspace/process-detail/ProcessDetailsPage';
import { AnalyticsWorkspaceLayout } from '@modules/workspace/layouts/AnalyticsWorkspaceLayout';
import { ReportsPage } from '@modules/reports/ReportsPage';
import { DashboardEventsPage } from '@modules/workspace/routes/DashboardEventsPage';
import { DashboardPostsPage } from '@modules/workspace/routes/DashboardPostsPage';
import { DashboardProcessesPage } from '@modules/workspace/routes/DashboardProcessesPage';
import type { AuthApiContract } from '@shared/auth/auth-api';
import type { TokenStorage } from '@shared/auth/token-storage';

type RenderAuthHarnessOptions = {
  authApi?: AuthApiContract;
  storage?: TokenStorage;
  initialEntry?: string;
  initialEntries?: string[];
  initialIndex?: number;
};

export function createMemoryTokenStorage(initialValue: unknown = null): TokenStorage {
  let currentValue = initialValue;

  return {
    load: () => currentValue as never,
    save: (tokens) => {
      currentValue = tokens;
    },
    clear: () => {
      currentValue = null;
    },
  };
}

export function renderAuthHarness({ authApi, storage, initialEntry, initialEntries, initialIndex }: RenderAuthHarnessOptions) {
  const entries = initialEntries ?? (initialEntry ? [initialEntry] : ['/']);

  return render(
    <ThemeProvider>
      <QueryClientProvider>
        <SessionProvider authApi={authApi} storage={storage}>
          <MemoryRouter initialEntries={entries} initialIndex={initialIndex}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <AuthGuard>
                    <AppShell />
                  </AuthGuard>
                }
              >
                <Route path="dashboard" element={<AnalyticsWorkspaceLayout />}>
                  <Route path="posts" element={<DashboardPostsPage />} />
                  <Route path="events" element={<DashboardEventsPage />} />
                  <Route path="processes" element={<DashboardProcessesPage />} />
                </Route>
                <Route path="posts/:postId" element={<PostDetailsPage />} />
                <Route path="events/:eventId" element={<EventDetailsPage />} />
                <Route path="processes/:processId" element={<ProcessDetailsPage />} />
                <Route path="reports/:reportType" element={<ReportsPage />} />
                <Route
                  path="channels"
                  element={
                    <RoleGuard routeId="channels">
                      <ChannelsPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="users"
                  element={
                    <RoleGuard routeId="users">
                      <UsersPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="settings"
                  element={
                    <RoleGuard routeId="settings">
                      <SettingsPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="monitor"
                  element={
                    <RoleGuard routeId="monitor">
                      <MonitorPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="jobs"
                  element={
                    <RoleGuard routeId="jobs">
                      <JobsPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="keyword-graph"
                  element={
                    <RoleGuard routeId="keywordGraph">
                      <KeywordGraphPage />
                    </RoleGuard>
                  }
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </SessionProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}
