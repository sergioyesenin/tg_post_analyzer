export const adminQueryKeys = {
  all: ['admin'] as const,
  channels: () => [...adminQueryKeys.all, 'channels'] as const,
  users: () => [...adminQueryKeys.all, 'users'] as const,
  settings: () => [...adminQueryKeys.all, 'settings'] as const,
  effectiveSettings: () => [...adminQueryKeys.all, 'settings', 'effective'] as const,
} as const;
