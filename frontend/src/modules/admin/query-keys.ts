import { sharedChannelsQueryKeys } from '@shared/channels/hooks';

export const adminQueryKeys = {
  all: ['admin'] as const,
  channels: () => sharedChannelsQueryKeys.list(),
  users: () => [...adminQueryKeys.all, 'users'] as const,
  settings: () => [...adminQueryKeys.all, 'settings'] as const,
  effectiveSettings: () => [...adminQueryKeys.all, 'settings', 'effective'] as const,
} as const;