export const userRoles = ['admin', 'analyst', 'viewer'] as const;

export type UserRole = (typeof userRoles)[number];

const rolePriority: Record<UserRole, number> = {
  admin: 3,
  analyst: 2,
  viewer: 1,
};

export function isUserRole(value: string): value is UserRole {
  return userRoles.includes(value as UserRole);
}

export function normalizeRoles(roles: string[]) {
  return roles.filter(isUserRole).sort((left, right) => rolePriority[right] - rolePriority[left]);
}

export function getPrimaryRole(roles: UserRole[]) {
  return roles[0] ?? null;
}

export function hasRequiredRole(userRolesList: UserRole[], allowedRoles: UserRole[]) {
  return allowedRoles.some((role) => userRolesList.includes(role));
}
