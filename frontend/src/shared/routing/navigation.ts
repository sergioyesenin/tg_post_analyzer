import type { UserRole } from '@shared/auth/roles';

type NavigationItem = {
  to: string;
  label: string;
  allowedRoles?: UserRole[];
};

export const dashboardModes: NavigationItem[] = [
  { to: '/dashboard/posts', label: 'Posts', allowedRoles: ['admin', 'analyst', 'viewer'] },
  { to: '/dashboard/events', label: 'Events', allowedRoles: ['admin', 'analyst', 'viewer'] },
  { to: '/dashboard/processes', label: 'Processes', allowedRoles: ['admin', 'analyst', 'viewer'] },
];

export const primaryNavigation: NavigationItem[] = [
  { to: '/dashboard/posts', label: 'Workspace', allowedRoles: ['admin', 'analyst', 'viewer'] },
  { to: '/reports/posts', label: 'Reports', allowedRoles: ['admin', 'analyst', 'viewer'] },
  { to: '/keyword-graph', label: 'Keyword graph', allowedRoles: ['admin', 'analyst'] },
];

export const secondaryNavigation: NavigationItem[] = [
  { to: '/channels', label: 'Channels', allowedRoles: ['admin'] },
  { to: '/users', label: 'Users', allowedRoles: ['admin'] },
  { to: '/settings', label: 'Settings', allowedRoles: ['admin', 'analyst'] },
  { to: '/monitor', label: 'Monitor', allowedRoles: ['admin'] },
  { to: '/jobs', label: 'Jobs', allowedRoles: ['admin'] },
];

export function canRenderNavigationItem(
  item: NavigationItem,
  roleSet: UserRole[],
) {
  if (!item.allowedRoles?.length) {
    return true;
  }

  return item.allowedRoles.some((role) => roleSet.includes(role));
}
