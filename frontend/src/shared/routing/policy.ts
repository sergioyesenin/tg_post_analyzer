import type { UserRole } from '@shared/auth/roles';
import { i18n } from '@shared/i18n/i18n';

export type RoutePolicyId =
  | 'login'
  | 'workspace.posts'
  | 'workspace.events'
  | 'workspace.processes'
  | 'details.post'
  | 'details.event'
  | 'details.process'
  | 'reports'
  | 'settings'
  | 'channels'
  | 'users'
  | 'monitor'
  | 'jobs'
  | 'keywordGraph';

export type NavigationSection = 'dashboard' | 'primary' | 'secondary';
export type AccessResolution = 'allowed' | 'redirected' | 'forbidden';
export type RouteCapability = 'read-only' | 'read-write';

type NavigationPolicy = {
  labelKey: string;
  section: NavigationSection;
};

type RoutePolicy = {
  id: RoutePolicyId;
  path: string;
  access: 'public' | 'protected';
  allowedRoles?: readonly UserRole[];
  unauthorizedBehavior: 'redirect' | 'forbidden';
  navigation?: NavigationPolicy;
  capabilities?: Partial<Record<UserRole, RouteCapability>>;
};

type ActionPolicy = {
  id: string;
  allowedRoles: readonly UserRole[];
  capabilityByRole: Partial<Record<UserRole, RouteCapability>>;
};

export type ActionPolicyId = (typeof actionPolicies)[number]['id'];

export const routePolicies: readonly RoutePolicy[] = [
  {
    id: 'login',
    path: '/login',
    access: 'public',
    unauthorizedBehavior: 'redirect',
  },
  {
    id: 'workspace.posts',
    path: '/dashboard/posts',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.posts', section: 'dashboard' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'workspace.events',
    path: '/dashboard/events',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.events', section: 'dashboard' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'workspace.processes',
    path: '/dashboard/processes',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.processes', section: 'dashboard' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'details.post',
    path: '/posts/:postId',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'details.event',
    path: '/events/:eventId',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'details.process',
    path: '/processes/:processId',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'reports',
    path: '/reports/posts',
    access: 'protected',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.reports', section: 'primary' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'keywordGraph',
    path: '/keyword-graph',
    access: 'protected',
    allowedRoles: ['admin', 'analyst'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.keywordGraph', section: 'primary' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-write',
    },
  },
  {
    id: 'settings',
    path: '/settings',
    access: 'protected',
    allowedRoles: ['admin', 'analyst'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.settings', section: 'secondary' },
    capabilities: {
      admin: 'read-write',
      analyst: 'read-only',
    },
  },
  {
    id: 'channels',
    path: '/channels',
    access: 'protected',
    allowedRoles: ['admin'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.channels', section: 'secondary' },
    capabilities: {
      admin: 'read-write',
    },
  },
  {
    id: 'users',
    path: '/users',
    access: 'protected',
    allowedRoles: ['admin'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.users', section: 'secondary' },
    capabilities: {
      admin: 'read-write',
    },
  },
  {
    id: 'monitor',
    path: '/monitor',
    access: 'protected',
    allowedRoles: ['admin'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.monitor', section: 'secondary' },
    capabilities: {
      admin: 'read-only',
    },
  },
  {
    id: 'jobs',
    path: '/jobs',
    access: 'protected',
    allowedRoles: ['admin'],
    unauthorizedBehavior: 'forbidden',
    navigation: { labelKey: 'navigation.jobs', section: 'secondary' },
    capabilities: {
      admin: 'read-write',
    },
  },
] as const;

export const actionPolicies: readonly ActionPolicy[] = [
  {
    id: 'dashboard.read',
    allowedRoles: ['admin', 'analyst', 'viewer'],
    capabilityByRole: {
      admin: 'read-write',
      analyst: 'read-write',
      viewer: 'read-only',
    },
  },
  {
    id: 'reports.generate',
    allowedRoles: ['admin', 'analyst'],
    capabilityByRole: {
      admin: 'read-write',
      analyst: 'read-write',
    },
  },
  {
    id: 'comments.refresh',
    allowedRoles: ['admin', 'analyst'],
    capabilityByRole: {
      admin: 'read-write',
      analyst: 'read-write',
    },
  },
  {
    id: 'settings.update',
    allowedRoles: ['admin'],
    capabilityByRole: {
      admin: 'read-write',
      analyst: 'read-only',
    },
  },
  {
    id: 'channels.manage',
    allowedRoles: ['admin'],
    capabilityByRole: {
      admin: 'read-write',
    },
  },
  {
    id: 'users.manage',
    allowedRoles: ['admin'],
    capabilityByRole: {
      admin: 'read-write',
    },
  },
  {
    id: 'jobs.retry',
    allowedRoles: ['admin'],
    capabilityByRole: {
      admin: 'read-write',
    },
  },
] as const;

export const defaultAuthenticatedRoute = '/dashboard/posts';

const routePolicyIndex = new Map(routePolicies.map((policy) => [policy.id, policy]));

export function getRoutePolicy(routeId: RoutePolicyId) {
  const policy = routePolicyIndex.get(routeId);

  if (!policy) {
    throw new Error(`Unknown route policy: ${routeId}`);
  }

  return policy;
}

export function canAccessRoute(routeId: RoutePolicyId, roles: readonly UserRole[]) {
  const policy = getRoutePolicy(routeId);

  if (policy.access === 'public') {
    return true;
  }

  return policy.allowedRoles?.some((role) => roles.includes(role)) ?? false;
}

export function resolveRouteAccess(
  routeId: RoutePolicyId,
  sessionStatus: 'guest' | 'authenticated',
  roles: readonly UserRole[],
): AccessResolution {
  const policy = getRoutePolicy(routeId);

  if (policy.access === 'public') {
    return sessionStatus === 'authenticated' ? 'redirected' : 'allowed';
  }

  if (sessionStatus !== 'authenticated') {
    return 'redirected';
  }

  if (canAccessRoute(routeId, roles)) {
    return 'allowed';
  }

  return policy.unauthorizedBehavior === 'forbidden' ? 'forbidden' : 'redirected';
}

export function getNavigationItems(section: NavigationSection, roles: readonly UserRole[]) {
  return routePolicies
    .filter((policy) => policy.navigation?.section === section)
    .filter((policy) => canAccessRoute(policy.id, roles))
    .map((policy) => ({
      id: policy.id,
      to: policy.path,
      label: i18n.t(policy.navigation!.labelKey),
    }));
}

export function getRouteCapability(routeId: RoutePolicyId, role: UserRole | null) {
  if (!role) {
    return null;
  }

  return getRoutePolicy(routeId).capabilities?.[role] ?? null;
}

export function canPerformAction(actionId: string, roles: readonly UserRole[]) {
  const policy = actionPolicies.find((item) => item.id === actionId);

  if (!policy) {
    throw new Error(`Unknown action policy: ${actionId}`);
  }

  return policy.allowedRoles.some((role) => roles.includes(role));
}

export function getActionCapability(actionId: string, role: UserRole | null) {
  if (!role) {
    return null;
  }

  const policy = actionPolicies.find((item) => item.id === actionId);

  if (!policy) {
    throw new Error(`Unknown action policy: ${actionId}`);
  }

  return policy.capabilityByRole[role] ?? null;
}
