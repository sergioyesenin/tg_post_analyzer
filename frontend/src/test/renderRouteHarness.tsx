import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { QueryClientProvider } from '@app/providers/QueryClientProvider';
import { SessionProvider, type SessionBootstrap } from '@app/providers/SessionProvider';
import { ThemeProvider } from '@app/providers/ThemeProvider';
import { AppShell } from '@app/shell/AppShell';
import { AuthGuard } from '@app/router/guards/AuthGuard';
import { RoleGuard } from '@app/router/guards/RoleGuard';
import { RootRedirect } from '@shared/routing/RootRedirect';
import { LoginPage } from '@modules/auth/routes/LoginPage';
import { ChannelsPlaceholderPage } from '@modules/platform/routes/ChannelsPlaceholderPage';
import { DashboardEventsPage } from '@modules/workspace/routes/DashboardEventsPage';
import { DashboardPostsPage } from '@modules/workspace/routes/DashboardPostsPage';

type HarnessOptions = {
  initialEntry: string;
  bootstrap: SessionBootstrap;
};

export function renderRouteHarness({ initialEntry, bootstrap }: HarnessOptions) {
  return render(
    <ThemeProvider>
      <QueryClientProvider>
        <SessionProvider bootstrap={bootstrap}>
          <MemoryRouter initialEntries={[initialEntry]}>
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
                <Route index element={<RootRedirect />} />
                <Route path="dashboard/posts" element={<DashboardPostsPage />} />
                <Route path="dashboard/events" element={<DashboardEventsPage />} />
                <Route
                  path="channels"
                  element={
                    <RoleGuard allowedRoles={['admin']}>
                      <ChannelsPlaceholderPage />
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
