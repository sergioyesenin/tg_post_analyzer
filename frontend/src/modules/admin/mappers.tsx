import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { ChannelDto, AdminUserDto, AppSettingDto } from '@modules/admin/contracts';
import { formatUtcDateTime } from '@shared/utils/formatters';

export const channelsColumns: DashboardTableColumn[] = [
  { id: 'channel', label: 'Channel' },
  { id: 'category', label: 'Category' },
  { id: 'active', label: 'Active' },
  { id: 'actions', label: 'Actions' },
];

export const usersColumns: DashboardTableColumn[] = [
  { id: 'user', label: 'User' },
  { id: 'roles', label: 'Roles' },
  { id: 'active', label: 'Active' },
  { id: 'created', label: 'Created' },
  { id: 'actions', label: 'Actions' },
];

export const settingsColumns: DashboardTableColumn[] = [
  { id: 'key', label: 'Key' },
  { id: 'description', label: 'Description' },
  { id: 'updated_by', label: 'Updated by' },
  { id: 'updated_at', label: 'Updated at' },
];

export function mapChannelsToRows(
  channels: ChannelDto[],
  selectedChannelId: number | null,
  onSelect: (channelId: number) => void,
): DashboardTableRow[] {
  return channels.map((channel) => ({
    id: String(channel.id),
    isSelected: channel.id === selectedChannelId,
    cells: {
      channel: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>@{channel.username}</strong>
          <span>{channel.title ?? 'n/a'}</span>
        </div>
      ),
      category: channel.category ?? 'n/a',
      active: channel.is_active ? 'yes' : 'no',
      actions: (
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={() => onSelect(channel.id)}>
          {channel.id === selectedChannelId ? 'Selected' : 'Manage'}
        </button>
      ),
    },
  }));
}

export function mapUsersToRows(
  users: AdminUserDto[],
  selectedUserId: number | null,
  onSelect: (userId: number) => void,
): DashboardTableRow[] {
  return users.map((user) => ({
    id: String(user.id),
    isSelected: user.id === selectedUserId,
    cells: {
      user: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{user.username}</strong>
          <span>{user.email ?? 'n/a'}</span>
        </div>
      ),
      roles: user.roles.join(', '),
      active: user.is_active ? 'yes' : 'no',
      created: formatUtcDateTime(user.created_at),
      actions: (
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={() => onSelect(user.id)}>
          {user.id === selectedUserId ? 'Selected' : 'Manage'}
        </button>
      ),
    },
  }));
}

export function mapSettingsToRows(settings: AppSettingDto[]): DashboardTableRow[] {
  return settings.map((setting) => ({
    id: setting.key,
    cells: {
      key: setting.key,
      description: setting.description ?? 'n/a',
      updated_by: setting.updated_by_user_id === null ? 'system' : String(setting.updated_by_user_id),
      updated_at: formatUtcDateTime(setting.updated_at),
    },
  }));
}
