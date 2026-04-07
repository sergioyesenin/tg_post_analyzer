import { i18n } from '@shared/i18n/i18n';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import type { ChannelDto, AdminUserDto, AppSettingDto } from '@modules/admin/contracts';
import {
  getSettingsCategoryMetadata,
  getSettingsFieldMetadataOrFallback,
  settingsCategoryOrder,
  type SettingsCategoryKey,
  type SettingsControlType,
  type SettingsFieldGroupHint,
  type SettingsUnit,
  type SettingsValueMetadata,
} from '@modules/admin/settings-registry';
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

export type SettingsParameterViewModel = {
  key: string;
  label: string;
  allowedValues: string;
  purpose: string;
  controlType: SettingsControlType;
  unit: SettingsUnit;
  valueMetadata: SettingsValueMetadata;
  order: number;
  groupHint?: SettingsFieldGroupHint;
  effectiveDisplayValue: string;
  editableDisplayValue: string;
  hasEditableValue: boolean;
  isDocumented: boolean;
};

export type SettingsCategoryViewModel = {
  key: SettingsCategoryKey;
  label: string;
  description: string;
  badge: string | null;
  parameterCount: number;
  configuredCount: number;
  parameters: SettingsParameterViewModel[];
  editableSetting: AppSettingDto | null;
  effectiveValue: Record<string, unknown>;
};

export function formatSettingValue(value: unknown): string {
  if (typeof value === 'boolean') {
    return value ? i18n.t('common.yes') : i18n.t('common.no');
  }

  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  if (typeof value === 'string') {
    return value;
  }

  if (value === null || value === undefined) {
    return i18n.t('common.na');
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function buildSettingsCategoryViewModels(
  settings: AppSettingDto[],
  effectiveSettings: Record<string, unknown>,
): SettingsCategoryViewModel[] {
  const settingsMap = new Map(settings.map((setting) => [setting.key, setting]));

  return settingsCategoryOrder.map((categoryKey) => {
    const metadata = getSettingsCategoryMetadata(categoryKey);
    const editableSetting = settingsMap.get(categoryKey) ?? null;
    const effectiveValue = asRecord(effectiveSettings[categoryKey]);
    const editableValue = asRecord(editableSetting?.value_json);
    const documentedKeys = new Set(metadata.fields.map((parameter) => parameter.key));
    const extraKeys = Array.from(new Set([...Object.keys(effectiveValue), ...Object.keys(editableValue)])).filter(
      (key) => !documentedKeys.has(key),
    );

    const parameters: SettingsParameterViewModel[] = [
      ...metadata.fields.map((parameter) => ({
        key: parameter.key,
        label: parameter.label,
        allowedValues: parameter.value.allowedValuesLabel,
        purpose: parameter.helperText ?? '',
        controlType: parameter.controlType,
        unit: parameter.unit,
        valueMetadata: parameter.value,
        order: parameter.order,
        groupHint: parameter.groupHint,
        effectiveDisplayValue: formatSettingValue(effectiveValue[parameter.key]),
        editableDisplayValue: formatSettingValue(editableValue[parameter.key]),
        hasEditableValue: Object.prototype.hasOwnProperty.call(editableValue, parameter.key),
        isDocumented: true,
      })),
      ...extraKeys.map((key, index) => {
        const parameter = getSettingsFieldMetadataOrFallback(categoryKey, key, metadata.fields.length + index + 1);

        return {
          key,
          label: parameter.label,
          allowedValues: parameter.value.allowedValuesLabel,
          purpose: parameter.helperText ?? i18n.t('admin.settings.fallbackPurpose'),
          controlType: parameter.controlType,
          unit: parameter.unit,
          valueMetadata: parameter.value,
          order: parameter.order,
          groupHint: parameter.groupHint,
          effectiveDisplayValue: formatSettingValue(effectiveValue[key]),
          editableDisplayValue: formatSettingValue(editableValue[key]),
          hasEditableValue: Object.prototype.hasOwnProperty.call(editableValue, key),
          isDocumented: false,
        };
      }),
    ];

    return {
      key: categoryKey,
      label: metadata.label,
      description: metadata.description,
      badge: metadata.badge ?? null,
      parameterCount: parameters.length,
      configuredCount: parameters.filter((parameter) => parameter.effectiveDisplayValue !== i18n.t('common.na')).length,
      parameters,
      editableSetting,
      effectiveValue,
    };
  });
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return {};
}
