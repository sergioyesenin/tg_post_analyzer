import { apiClient } from '@shared/api/client';
import type {
  AdminUserDto,
  AppSettingDto,
  CreateUserDto,
  UpdateSettingDto,
  UpdateUserRolesDto,
} from '@modules/admin/contracts';

export {
  addChannel,
  deleteChannel,
  getChannels,
  setChannelActive,
  updateChannel,
} from '@shared/channels/api';

export type {
  AddChannelDto,
  AddChannelResponseDto,
  ChannelDto,
  DeleteChannelResponseDto,
  UpdateChannelDto,
} from '@shared/channels/contracts';

export function getUsers() {
  return apiClient.get<AdminUserDto[]>('/api/auth/users');
}

export function createUser(payload: CreateUserDto) {
  return apiClient.post<AdminUserDto>('/api/auth/users', payload);
}

export function updateUserRoles(userId: number, payload: UpdateUserRolesDto) {
  return apiClient.put<AdminUserDto>(`/api/auth/users/${userId}/roles`, payload);
}

export function setUserActive(userId: number, active: boolean) {
  return apiClient.put<AdminUserDto>(`/api/auth/users/${userId}/active?active=${String(active)}`);
}

export function getSettings() {
  return apiClient.get<AppSettingDto[]>('/api/settings/');
}

export function getEffectiveSettings() {
  return apiClient.get<Record<string, unknown>>('/api/settings/effective');
}

export function updateSetting(key: string, payload: UpdateSettingDto) {
  return apiClient.put<AppSettingDto>(`/api/settings/${key}`, payload);
}