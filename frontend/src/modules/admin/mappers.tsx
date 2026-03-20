import { i18n } from '@shared/i18n/i18n';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import type { ChannelDto, AdminUserDto, AppSettingDto } from '@modules/admin/contracts';
import { formatUtcDateTime } from '@shared/utils/formatters';

export const channelsColumns: DataTableColumn[] = [
  { id: 'channel', label: i18n.t('admin.channels.table.channel') },
  { id: 'category', label: i18n.t('admin.channels.table.category') },
  { id: 'active', label: i18n.t('admin.channels.table.active') },
  { id: 'actions', label: i18n.t('admin.channels.table.actions') },
];

export const usersColumns: DataTableColumn[] = [
  { id: 'user', label: i18n.t('admin.users.table.user') },
  { id: 'roles', label: i18n.t('admin.users.table.roles') },
  { id: 'active', label: i18n.t('admin.users.table.active') },
  { id: 'created', label: i18n.t('admin.users.table.created') },
  { id: 'actions', label: i18n.t('admin.users.table.actions') },
];

export const settingsColumns: DataTableColumn[] = [
  { id: 'key', label: i18n.t('admin.settings.table.key') },
  { id: 'description', label: i18n.t('admin.settings.table.description') },
  { id: 'updated_by', label: i18n.t('admin.settings.table.updatedBy') },
  { id: 'updated_at', label: i18n.t('admin.settings.table.updatedAt') },
];

export function mapChannelsToRows(
  channels: ChannelDto[],
  selectedChannelId: number | null,
  onSelect: (channelId: number) => void,
): DataTableRow[] {
  return channels.map((channel) => ({
    id: String(channel.id),
    isSelected: channel.id === selectedChannelId,
    cells: {
      channel: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>@{channel.username}</strong>
          <span>{channel.title ?? i18n.t('common.na')}</span>
        </div>
      ),
      category: channel.category ?? i18n.t('common.na'),
      active: channel.is_active ? i18n.t('common.yes') : i18n.t('common.no'),
      actions: (
        <button
          type="button"
          className={`admin-console-button admin-console-button--secondary admin-console-button--table ${
            channel.id === selectedChannelId ? 'admin-console-button--selected' : ''
          }`.trim()}
          onClick={() => onSelect(channel.id)}
        >
          {channel.id === selectedChannelId ? i18n.t('common.selected') : i18n.t('admin.common.manage')}
        </button>
      ),
    },
  }));
}

export function mapUsersToRows(
  users: AdminUserDto[],
  selectedUserId: number | null,
  onSelect: (userId: number) => void,
): DataTableRow[] {
  return users.map((user) => ({
    id: String(user.id),
    isSelected: user.id === selectedUserId,
    cells: {
      user: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{user.username}</strong>
          <span>{user.email ?? i18n.t('common.na')}</span>
        </div>
      ),
      roles: user.roles.map((role) => i18n.t(`admin.roles.${role}`)).join(', '),
      active: user.is_active ? i18n.t('common.yes') : i18n.t('common.no'),
      created: formatUtcDateTime(user.created_at),
      actions: (
        <button
          type="button"
          className={`admin-console-button admin-console-button--secondary admin-console-button--table ${
            user.id === selectedUserId ? 'admin-console-button--selected' : ''
          }`.trim()}
          onClick={() => onSelect(user.id)}
        >
          {user.id === selectedUserId ? i18n.t('common.selected') : i18n.t('admin.common.manage')}
        </button>
      ),
    },
  }));
}

export function mapSettingsToRows(settings: AppSettingDto[]): DataTableRow[] {
  return settings.map((setting) => ({
    id: setting.key,
    cells: {
      key: setting.key,
      description: setting.description ?? i18n.t('common.na'),
      updated_by: setting.updated_by_user_id === null ? i18n.t('admin.common.system') : String(setting.updated_by_user_id),
      updated_at: formatUtcDateTime(setting.updated_at),
    },
  }));
}

