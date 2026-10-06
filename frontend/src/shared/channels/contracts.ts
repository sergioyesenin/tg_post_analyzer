import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export type ChannelDto = {
  id: number;
  username: string;
  title: string | null;
  category: string | null;
  is_active: boolean;
};

export type AddChannelDto = {
  username: string;
};

export type AddChannelResponseDto = AcceptedJobResponse;

export type UpdateChannelDto = {
  title?: string | null;
  category?: string | null;
  is_active?: boolean | null;
};

export type DeleteChannelResponseDto = {
  status: string;
  channel_id: number;
  username: string | null;
};