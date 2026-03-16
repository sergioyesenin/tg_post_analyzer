import { Suspense, lazy, type ComponentType, type ReactNode } from 'react';
import { RouterProvider, createBrowserRouter, createMemoryRouter } from 'react-router-dom';

import { AuthGuard } from '@app/router/guards/AuthGuard';
import { RoleGuard } from '@app/router/guards/RoleGuard';
import { AppShell } from '@app/shell/AppShell';
import { getRoutePolicy } from '@shared/routing/policy';
import { RootRedirect } from '@shared/routing/RootRedirect';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { NotFoundPage } from '@shared/ui/states/NotFoundPage';

type LazyModule = Record<string, unknown>;

function lazyRoute<TModule extends LazyModule, TKey extends keyof TModule>(
  loader: () => Promise<TModule>,
  exportName: TKey,
) {
  return lazy(async () => {
    const module = await loader();

    return {
      default: module[exportName] as ComponentType,
    };
  });
}

function withRouteSuspense(element: ReactNode) {
  return (
    <Suspense
      fallback={<LoadingState title="Loading route" description="Preparing the selected screen." />}
    >
      {element}
    </Suspense>
  );
}

const LoginPage = lazyRoute(() => import('@modules/auth/routes/LoginPage'), 'LoginPage');
const AnalyticsWorkspaceLayout = lazyRoute(
  () => import('@modules/workspace/layouts/AnalyticsWorkspaceLayout'),
  'AnalyticsWorkspaceLayout',
);
const DashboardPostsPage = lazyRoute(() => import('@modules/workspace/routes/DashboardPostsPage'), 'DashboardPostsPage');
const DashboardEventsPage = lazyRoute(() => import('@modules/workspace/routes/DashboardEventsPage'), 'DashboardEventsPage');
const DashboardProcessesPage = lazyRoute(
  () => import('@modules/workspace/routes/DashboardProcessesPage'),
  'DashboardProcessesPage',
);
const PostDetailsPage = lazyRoute(() => import('@modules/workspace/post-detail/PostDetailsPage'), 'PostDetailsPage');
const EventDetailsPage = lazyRoute(() => import('@modules/workspace/event-detail/EventDetailsPage'), 'EventDetailsPage');
const ProcessDetailsPage = lazyRoute(
  () => import('@modules/workspace/process-detail/ProcessDetailsPage'),
  'ProcessDetailsPage',
);
const ReportsPage = lazyRoute(() => import('@modules/reports/ReportsPage'), 'ReportsPage');
const SettingsPage = lazyRoute(() => import('@modules/admin/routes/SettingsPage'), 'SettingsPage');
const ChannelsPage = lazyRoute(() => import('@modules/admin/routes/ChannelsPage'), 'ChannelsPage');
const UsersPage = lazyRoute(() => import('@modules/admin/routes/UsersPage'), 'UsersPage');
const MonitorPage = lazyRoute(() => import('@modules/platform/routes/MonitorPage'), 'MonitorPage');
const JobsPage = lazyRoute(() => import('@modules/platform/routes/JobsPage'), 'JobsPage');
const KeywordGraphPage = lazyRoute(() => import('@modules/keyword-graph/KeywordGraphPage'), 'KeywordGraphPage');

const routes = [
  {
    path: getRoutePolicy('login').path,
    element: withRouteSuspense(<LoginPage />),
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
        element: withRouteSuspense(<AnalyticsWorkspaceLayout />),
        children: [
          {
            path: 'posts',
            element: withRouteSuspense(<DashboardPostsPage />),
          },
          {
            path: 'events',
            element: withRouteSuspense(<DashboardEventsPage />),
          },
          {
            path: 'processes',
            element: withRouteSuspense(<DashboardProcessesPage />),
          },
        ],
      },
      {
        path: 'posts/:postId',
        element: withRouteSuspense(<PostDetailsPage />),
      },
      {
        path: 'events/:eventId',
        element: withRouteSuspense(<EventDetailsPage />),
      },
      {
        path: 'processes/:processId',
        element: withRouteSuspense(<ProcessDetailsPage />),
      },
      {
        path: 'reports/:reportType',
        element: withRouteSuspense(<ReportsPage />),
      },
      {
        path: 'settings',
        element: (
          <RoleGuard routeId="settings">
            {withRouteSuspense(<SettingsPage />)}
          </RoleGuard>
        ),
      },
      {
        path: 'channels',
        element: (
          <RoleGuard routeId="channels">
            {withRouteSuspense(<ChannelsPage />)}
          </RoleGuard>
        ),
      },
      {
        path: 'users',
        element: (
          <RoleGuard routeId="users">
            {withRouteSuspense(<UsersPage />)}
          </RoleGuard>
        ),
      },
      {
        path: 'monitor',
        element: (
          <RoleGuard routeId="monitor">
            {withRouteSuspense(<MonitorPage />)}
          </RoleGuard>
        ),
      },
      {
        path: 'jobs',
        element: (
          <RoleGuard routeId="jobs">
            {withRouteSuspense(<JobsPage />)}
          </RoleGuard>
        ),
      },
      {
        path: 'keyword-graph',
        element: (
          <RoleGuard routeId="keywordGraph">
            {withRouteSuspense(<KeywordGraphPage />)}
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

