export const userRoles = ['admin', 'analyst', 'viewer'] as const;

export type UserRole = (typeof userRoles)[number];
