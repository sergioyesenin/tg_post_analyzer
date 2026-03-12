import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { QueryClientProvider } from '@app/providers/QueryClientProvider';
import { SessionProvider } from '@app/providers/SessionProvider';
import { ThemeProvider } from '@app/providers/ThemeProvider';
import { AuthGuard } from '@app/router/guards/AuthGuard';
import { RoleGuard } from '@app/router/guards/RoleGuard';
import { AppShell } from '@app/shell/AppShell';
import { LoginPage } from '@modules/auth/routes/LoginPage';
import { ChannelsPlaceholderPage } from '@modules/platform/routes/ChannelsPlaceholderPage';
import { KeywordGraphPlaceholderPage } from '@modules/platform/routes/KeywordGraphPlaceholderPage';
import { PostDetailsPage } from '@modules/workspace/post-detail/PostDetailsPage';
import { AnalyticsWorkspaceLayout } from '@modules/workspace/layouts/AnalyticsWorkspaceLayout';
import { DashboardEventsPage } from '@modules/workspace/routes/DashboardEventsPage';
import { DashboardPostsPage } from '@modules/workspace/routes/DashboardPostsPage';
import { DashboardProcessesPage } from '@modules/workspace/routes/DashboardProcessesPage';
import type { AuthApiContract } from '@shared/auth/auth-api';
import type { TokenStorage } from '@shared/auth/token-storage';

type RenderAuthHarnessOptions = {
  authApi?: AuthApiContract;
  storage?: TokenStorage;
  initialEntry: string;
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

export function renderAuthHarness({ authApi, storage, initialEntry }: RenderAuthHarnessOptions) {
  return render(
    <ThemeProvider>
      <QueryClientProvider>
        <SessionProvider authApi={authApi} storage={storage}>
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
                <Route path="dashboard" element={<AnalyticsWorkspaceLayout />}>
                  <Route path="posts" element={<DashboardPostsPage />} />
                  <Route path="events" element={<DashboardEventsPage />} />
                  <Route path="processes" element={<DashboardProcessesPage />} />
                </Route>
                <Route path="posts/:postId" element={<PostDetailsPage />} />
                <Route
                  path="channels"
                  element={
                    <RoleGuard routeId="channels">
                      <ChannelsPlaceholderPage />
                    </RoleGuard>
                  }
                />
                <Route
                  path="keyword-graph"
                  element={
                    <RoleGuard routeId="keywordGraph">
                      <KeywordGraphPlaceholderPage />
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
