import { RouterProvider, createBrowserRouter, createMemoryRouter } from 'react-router-dom';

import { AuthGuard } from '@app/router/guards/AuthGuard';
import { RoleGuard } from '@app/router/guards/RoleGuard';
import { AppShell } from '@app/shell/AppShell';
import { ChannelsPage } from '@modules/admin/routes/ChannelsPage';
import { SettingsPage } from '@modules/admin/routes/SettingsPage';
import { UsersPage } from '@modules/admin/routes/UsersPage';
import { LoginPage } from '@modules/auth/routes/LoginPage';
import { JobsPage } from '@modules/platform/routes/JobsPage';
import { KeywordGraphPlaceholderPage } from '@modules/platform/routes/KeywordGraphPlaceholderPage';
import { MonitorPage } from '@modules/platform/routes/MonitorPage';
import { ReportsPage } from '@modules/reports/ReportsPage';
import { AnalyticsWorkspaceLayout } from '@modules/workspace/layouts/AnalyticsWorkspaceLayout';
import { DashboardEventsPage } from '@modules/workspace/routes/DashboardEventsPage';
import { DashboardPostsPage } from '@modules/workspace/routes/DashboardPostsPage';
import { DashboardProcessesPage } from '@modules/workspace/routes/DashboardProcessesPage';
import { EventDetailsPage } from '@modules/workspace/event-detail/EventDetailsPage';
import { PostDetailsPage } from '@modules/workspace/post-detail/PostDetailsPage';
import { ProcessDetailsPage } from '@modules/workspace/process-detail/ProcessDetailsPage';
import { getRoutePolicy } from '@shared/routing/policy';
import { RootRedirect } from '@shared/routing/RootRedirect';
import { NotFoundPage } from '@shared/ui/states/NotFoundPage';

const routes = [
  {
    path: getRoutePolicy('login').path,
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <AppShell />
      </AuthGuard>
    ),
    children: [
      {
        index: true,
        element: <RootRedirect />,
      },
      {
        path: 'dashboard',
        element: <AnalyticsWorkspaceLayout />,
        children: [
          {
            path: 'posts',
            element: <DashboardPostsPage />,
          },
          {
            path: 'events',
            element: <DashboardEventsPage />,
          },
          {
            path: 'processes',
            element: <DashboardProcessesPage />,
          },
        ],
      },
      {
        path: 'posts/:postId',
        element: <PostDetailsPage />,
      },
      {
        path: 'events/:eventId',
        element: <EventDetailsPage />,
      },
      {
        path: 'processes/:processId',
        element: <ProcessDetailsPage />,
      },
      {
        path: 'reports/:reportType',
        element: <ReportsPage />,
      },
      {
        path: 'settings',
        element: (
          <RoleGuard routeId="settings">
            <SettingsPage />
          </RoleGuard>
        ),
      },
      {
        path: 'channels',
        element: (
          <RoleGuard routeId="channels">
            <ChannelsPage />
          </RoleGuard>
        ),
      },
      {
        path: 'users',
        element: (
          <RoleGuard routeId="users">
            <UsersPage />
          </RoleGuard>
        ),
      },
      {
        path: 'monitor',
        element: (
          <RoleGuard routeId="monitor">
            <MonitorPage />
          </RoleGuard>
        ),
      },
      {
        path: 'jobs',
        element: (
          <RoleGuard routeId="jobs">
            <JobsPage />
          </RoleGuard>
        ),
      },
      {
        path: 'keyword-graph',
        element: (
          <RoleGuard routeId="keywordGraph">
            <KeywordGraphPlaceholderPage />
          </RoleGuard>
        ),
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
];

function createAppRouter() {
  if (import.meta.env.MODE === 'test') {
    return createMemoryRouter(routes, {
      initialEntries: [window.location.pathname + window.location.search],
    });
  }

  return createBrowserRouter(routes);
}

export function AppRouter() {
  return <RouterProvider router={createAppRouter()} />;
}
