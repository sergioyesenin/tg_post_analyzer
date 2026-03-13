import { apiClient } from '@shared/api/client';
import type {
  AddChannelDto,
  AdminUserDto,
  AppSettingDto,
  ChannelDto,
  CreateUserDto,
  DeleteChannelResponseDto,
  UpdateChannelDto,
  UpdateSettingDto,
  UpdateUserRolesDto,
} from '@modules/admin/contracts';

export function getChannels() {
  return apiClient.get<ChannelDto[]>('/api/channels/');
}

export function addChannel(payload: AddChannelDto) {
  return apiClient.post<string>('/api/channels/add', payload);
}

export function updateChannel(channelId: number, payload: UpdateChannelDto) {
  return apiClient.patch<ChannelDto>(`/api/channels/${channelId}`, payload);
}

export function setChannelActive(channelId: number, isActive: boolean) {
  return apiClient.put<ChannelDto>(`/api/channels/${channelId}/active?is_active=${String(isActive)}`);
}

export function deleteChannel(channelId: number) {
  return apiClient.delete<DeleteChannelResponseDto>(`/api/channels/${channelId}`);
}

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
