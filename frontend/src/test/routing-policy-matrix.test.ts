import { describe, expect, it } from 'vitest';

import type { UserRole } from '@shared/auth/roles';
import {
  canPerformAction,
  defaultAuthenticatedRoute,
  getActionCapability,
  getRouteCapability,
  resolveRouteAccess,
  routePolicies,
} from '@shared/routing/policy';

const protectedRouteIds = routePolicies.filter((policy) => policy.access === 'protected').map((policy) => policy.id);

type RouteExpectation = {
  routeId: (typeof protectedRouteIds)[number];
  admin: 'allowed' | 'forbidden';
  analyst: 'allowed' | 'forbidden';
  viewer: 'allowed' | 'forbidden';
};

const routeMatrix: RouteExpectation[] = [
  { routeId: 'workspace.posts', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'workspace.events', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'workspace.processes', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'details.post', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'details.event', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'details.process', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'reports', admin: 'allowed', analyst: 'allowed', viewer: 'allowed' },
  { routeId: 'keywordGraph', admin: 'allowed', analyst: 'allowed', viewer: 'forbidden' },
  { routeId: 'settings', admin: 'allowed', analyst: 'allowed', viewer: 'forbidden' },
  { routeId: 'channels', admin: 'allowed', analyst: 'forbidden', viewer: 'forbidden' },
  { routeId: 'users', admin: 'allowed', analyst: 'forbidden', viewer: 'forbidden' },
  { routeId: 'monitor', admin: 'allowed', analyst: 'forbidden', viewer: 'forbidden' },
  { routeId: 'jobs', admin: 'allowed', analyst: 'forbidden', viewer: 'forbidden' },
];

describe('Routing policy matrix', () => {
  it('keeps the expected route inventory for the implemented frontend modules', () => {
    expect(routePolicies.map((policy) => [policy.id, policy.path])).toEqual([
      ['login', '/login'],
      ['workspace.posts', '/dashboard/posts'],
      ['workspace.events', '/dashboard/events'],
      ['workspace.processes', '/dashboard/processes'],
      ['details.post', '/posts/:postId'],
      ['details.event', '/events/:eventId'],
      ['details.process', '/processes/:processId'],
      ['reports', '/reports/posts'],
      ['keywordGraph', '/keyword-graph'],
      ['settings', '/settings'],
      ['channels', '/channels'],
      ['users', '/users'],
      ['monitor', '/monitor'],
      ['jobs', '/jobs'],
    ]);

    expect(defaultAuthenticatedRoute).toBe('/dashboard/posts');
  });

  it('resolves protected route access according to the major RBAC matrix', () => {
    const roleSets: Record<UserRole, readonly UserRole[]> = {
      admin: ['admin'],
      analyst: ['analyst'],
      viewer: ['viewer'],
    };

    for (const item of routeMatrix) {
      expect(resolveRouteAccess(item.routeId, 'guest', [])).toBe('redirected');
      expect(resolveRouteAccess(item.routeId, 'authenticated', roleSets.admin)).toBe(item.admin);
      expect(resolveRouteAccess(item.routeId, 'authenticated', roleSets.analyst)).toBe(item.analyst);
      expect(resolveRouteAccess(item.routeId, 'authenticated', roleSets.viewer)).toBe(item.viewer);
    }
  });

  it('exposes route capability tiers for writable and read-only surfaces', () => {
    expect(getRouteCapability('workspace.posts', 'admin')).toBe('read-write');
    expect(getRouteCapability('workspace.posts', 'viewer')).toBe('read-only');
    expect(getRouteCapability('settings', 'analyst')).toBe('read-only');
    expect(getRouteCapability('monitor', 'admin')).toBe('read-only');
    expect(getRouteCapability('keywordGraph', 'viewer')).toBeNull();
  });

  it('keeps action-level RBAC aligned with async/report/admin flows', () => {
    expect(canPerformAction('dashboard.read', ['viewer'])).toBe(true);
    expect(canPerformAction('reports.generate', ['analyst'])).toBe(true);
    expect(canPerformAction('comments.refresh', ['viewer'])).toBe(false);
    expect(canPerformAction('settings.update', ['analyst'])).toBe(false);
    expect(canPerformAction('jobs.retry', ['admin'])).toBe(true);
    expect(canPerformAction('jobs.retry', ['analyst'])).toBe(false);

    expect(getActionCapability('reports.generate', 'admin')).toBe('read-write');
    expect(getActionCapability('comments.refresh', 'analyst')).toBe('read-write');
    expect(getActionCapability('settings.update', 'analyst')).toBe('read-only');
    expect(getActionCapability('jobs.retry', 'viewer')).toBeNull();
  });
});
