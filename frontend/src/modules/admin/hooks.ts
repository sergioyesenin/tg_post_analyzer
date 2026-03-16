import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  addChannel,
  createUser,
  deleteChannel,
  getChannels,
  getEffectiveSettings,
  getSettings,
  getUsers,
  setChannelActive,
  setUserActive,
  updateChannel,
  updateSetting,
  updateUserRoles,
} from '@modules/admin/api';
import type {
  AddChannelDto,
  CreateUserDto,
  UpdateChannelDto,
  UpdateSettingDto,
  UpdateUserRolesDto,
} from '@modules/admin/contracts';
import { adminQueryKeys } from '@modules/admin/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';

export function useChannelsQuery() {
  return useQuery({
    queryKey: adminQueryKeys.channels(),
    queryFn: getChannels,
    retry: false,
  });
}

export function useChannelMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: adminQueryKeys.channels() });

  return {
    add: useAsyncJobAction({
      actionLabel: 'add-channel',
      mutationFn: (payload: AddChannelDto) => addChannel(payload),
      onInvalidate: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ channelId, payload }: { channelId: number; payload: UpdateChannelDto }) => updateChannel(channelId, payload),
      onSuccess: invalidate,
    }),
    setActive: useMutation({
      mutationFn: ({ channelId, isActive }: { channelId: number; isActive: boolean }) => setChannelActive(channelId, isActive),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (channelId: number) => deleteChannel(channelId),
      onSuccess: invalidate,
    }),
  };
}

export function useUsersQuery() {
  return useQuery({
    queryKey: adminQueryKeys.users(),
    queryFn: getUsers,
    retry: false,
  });
}

export function useUserMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: adminQueryKeys.users() });

  return {
    create: useMutation({
      mutationFn: (payload: CreateUserDto) => createUser(payload),
      onSuccess: invalidate,
    }),
    updateRoles: useMutation({
      mutationFn: ({ userId, payload }: { userId: number; payload: UpdateUserRolesDto }) => updateUserRoles(userId, payload),
      onSuccess: invalidate,
    }),
    setActive: useMutation({
      mutationFn: ({ userId, active }: { userId: number; active: boolean }) => setUserActive(userId, active),
      onSuccess: invalidate,
    }),
  };
}

export function useSettingsQueries(isAdmin: boolean) {
  const [effectiveQuery, settingsQuery] = useQueries({
    queries: [
      {
        queryKey: adminQueryKeys.effectiveSettings(),
        queryFn: getEffectiveSettings,
        retry: false,
      },
      {
        queryKey: adminQueryKeys.settings(),
        queryFn: getSettings,
        retry: false,
        enabled: isAdmin,
      },
    ],
  });

  return { effectiveQuery, settingsQuery };
}

export function useSettingsMutations() {
  const queryClient = useQueryClient();
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.settings() }),
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.effectiveSettings() }),
    ]);
  };

  return {
    update: useMutation({
      mutationFn: ({ key, payload }: { key: string; payload: UpdateSettingDto }) => updateSetting(key, payload),
      onSuccess: invalidate,
    }),
  };
}
