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

export type AdminUserDto = {
  id: number;
  username: string;
  email: string | null;
  full_name: string | null;
  is_active: boolean;
  is_local: boolean;
  roles: string[];
  created_at: string;
};

export type CreateUserDto = {
  username: string;
  password: string;
  email: string | null;
  full_name: string | null;
  roles: string[];
};

export type UpdateUserRolesDto = {
  roles: string[];
};

export type AppSettingDto = {
  key: string;
  value_json: Record<string, unknown>;
  description: string | null;
  updated_by_user_id: number | null;
  updated_at: string;
};

export type UpdateSettingDto = {
  value_json: Record<string, unknown>;
  description: string | null;
};
