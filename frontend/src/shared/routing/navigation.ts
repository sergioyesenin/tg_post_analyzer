export const dashboardModes = [
  { to: '/dashboard/posts', label: 'Posts' },
  { to: '/dashboard/events', label: 'Events' },
  { to: '/dashboard/processes', label: 'Processes' },
] as const;

export const primaryNavigation = [
  { to: '/dashboard/posts', label: 'Workspace' },
  { to: '/reports/posts', label: 'Reports' },
  { to: '/keyword-graph', label: 'Keyword graph' },
] as const;

export const secondaryNavigation = [
  { to: '/channels', label: 'Channels' },
  { to: '/users', label: 'Users' },
  { to: '/settings', label: 'Settings' },
  { to: '/monitor', label: 'Monitor' },
  { to: '/jobs', label: 'Jobs' },
] as const;
