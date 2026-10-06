import { apiClient } from '@shared/api/client';
import type {
  AddChannelDto,
  AddChannelResponseDto,
  ChannelDto,
  DeleteChannelResponseDto,
  UpdateChannelDto,
} from '@shared/channels/contracts';

export function getChannels() {
  return apiClient.get<ChannelDto[]>('/api/channels/');
}

export function addChannel(payload: AddChannelDto) {
  return apiClient.post<AddChannelResponseDto>('/api/channels/add', payload);
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