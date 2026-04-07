import { z } from 'zod';

import {
  getSettingsFieldMetadata,
  type SettingsCategoryKey,
  type SettingsFieldMetadata,
  type SettingsValueMetadata,
} from '@modules/admin/settings-registry';
import { ApiError } from '@shared/api/client';
import { i18n } from '@shared/i18n/i18n';

export const addChannelSchema = z.object({
  username: z.string().trim().min(1, i18n.t('admin.validation.usernameRequired')),
});

export const updateChannelSchema = z.object({
  title: z.string().trim().optional().or(z.literal('')),
  category: z.string().trim().optional().or(z.literal('')),
  is_active: z.boolean(),
});

export const createUserSchema = z.object({
  username: z.string().trim().min(1, i18n.t('admin.validation.usernameRequired')),
  password: z.string().min(8, i18n.t('admin.validation.passwordMin')),
  email: z.string().email(i18n.t('admin.validation.emailInvalid')).optional().or(z.literal('')),
  full_name: z.string().optional().or(z.literal('')),
  roles: z.array(z.enum(['admin', 'analyst', 'viewer'])).min(1, i18n.t('admin.validation.roleRequired')),
});

export const updateUserRolesSchema = z.object({
  roles: z.array(z.enum(['admin', 'analyst', 'viewer'])).min(1, i18n.t('admin.validation.roleRequired')),
});

export const updateSettingSchema = z.object({
  description: z.string().optional().or(z.literal('')),
  value_json_text: z
    .string()
    .trim()
    .min(2, i18n.t('admin.validation.jsonRequired'))
    .refine((value) => {
      try {
        const parsed = JSON.parse(value);
        return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed);
      } catch {
        return false;
      }
    }, i18n.t('admin.validation.jsonObjectInvalid')),
});

export type SettingsFieldValidationErrors = Record<string, string>;

export type SettingsMutationErrorState = {
  fieldErrors: SettingsFieldValidationErrors;
  sectionError: string | null;
  serverError: string | null;
};

export function parseSettingsPayload(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value);
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }

  return null;
}

export function validateSettingsPayload(
  categoryKey: SettingsCategoryKey,
  payload: Record<string, unknown>,
): SettingsFieldValidationErrors {
  const errors: SettingsFieldValidationErrors = {};

  Object.entries(payload).forEach(([fieldKey, fieldValue]) => {
    const metadata = getSettingsFieldMetadata(categoryKey, fieldKey);

    if (!metadata) {
      return;
    }

    const message = validateFieldValue(metadata, fieldValue);
    if (message) {
      errors[fieldKey] = message;
    }
  });

  return errors;
}

export function mapSettingsMutationError(
  error: unknown,
  categoryKey: SettingsCategoryKey,
  payload: Record<string, unknown>,
): SettingsMutationErrorState {
  if (!(error instanceof ApiError)) {
    return {
      fieldErrors: {},
      sectionError: null,
      serverError: i18n.t('admin.settings.saveNetworkError'),
    };
  }

  if (error.status !== 422) {
    return {
      fieldErrors: {},
      sectionError: null,
      serverError: i18n.t('admin.settings.saveServerError'),
    };
  }

  const clientErrors = validateSettingsPayload(categoryKey, payload);
  const backendFieldErrors: SettingsFieldValidationErrors = {};
  const sectionMessages: string[] = [];
  const entries = extractBackendValidationEntries(error.payload);

  entries.forEach((entry) => {
    const fieldKey = findKnownFieldKey(categoryKey, entry.path);

    if (fieldKey) {
      const metadata = getSettingsFieldMetadata(categoryKey, fieldKey);
      if (metadata) {
        backendFieldErrors[fieldKey] = clientErrors[fieldKey] ?? getBackendFieldMessage(metadata, entry.message);
      }
      return;
    }

    sectionMessages.push(localizeBackendMessage(entry.message) ?? i18n.t('admin.settings.saveValidationError'));
  });

  if (Object.keys(clientErrors).length > 0) {
    return {
      fieldErrors: { ...backendFieldErrors, ...clientErrors },
      sectionError: sectionMessages[0] ?? i18n.t('admin.settings.saveValidationError'),
      serverError: null,
    };
  }

  if (Object.keys(backendFieldErrors).length > 0 || sectionMessages.length > 0) {
    return {
      fieldErrors: backendFieldErrors,
      sectionError: sectionMessages[0] ?? i18n.t('admin.settings.saveValidationError'),
      serverError: null,
    };
  }

  return {
    fieldErrors: {},
    sectionError: i18n.t('admin.settings.saveValidationError'),
    serverError: null,
  };
}

export type AddChannelFormValues = z.infer<typeof addChannelSchema>;
export type UpdateChannelFormValues = z.infer<typeof updateChannelSchema>;
export type CreateUserFormValues = z.infer<typeof createUserSchema>;
export type UpdateUserRolesFormValues = z.infer<typeof updateUserRolesSchema>;
export type UpdateSettingFormValues = z.infer<typeof updateSettingSchema>;

function validateFieldValue(metadata: SettingsFieldMetadata, value: unknown): string | null {
  if (value === undefined || metadata.value.kind === 'unknown') {
    return null;
  }

  if (metadata.value.kind === 'boolean') {
    return typeof value === 'boolean' ? null : i18n.t('admin.validation.settingsBoolean', { label: metadata.label });
  }

  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return metadata.value.kind === 'integer'
      ? i18n.t('admin.validation.settingsInteger', { label: metadata.label })
      : i18n.t('admin.validation.settingsFloat', { label: metadata.label });
  }

  if (metadata.value.kind === 'integer' && !Number.isInteger(value)) {
    return i18n.t('admin.validation.settingsInteger', { label: metadata.label });
  }

  return validateRange(metadata.label, metadata.value, value);
}

function validateRange(
  label: string,
  metadata: Extract<SettingsValueMetadata, { kind: 'integer' | 'float' }>,
  value: number,
): string | null {
  if (value < metadata.min || value > metadata.max) {
    return i18n.t('admin.validation.settingsRange', {
      label,
      min: metadata.min,
      max: metadata.max,
    });
  }

  return null;
}

function findKnownFieldKey(categoryKey: SettingsCategoryKey, path: string[]): string | null {
  for (let index = path.length - 1; index >= 0; index -= 1) {
    const candidate = path[index];
    if (candidate && getSettingsFieldMetadata(categoryKey, candidate)) {
      return candidate;
    }
  }

  return null;
}

function getBackendFieldMessage(metadata: SettingsFieldMetadata, backendMessage: string | null): string {
  return localizeBackendMessage(backendMessage) ?? defaultBackendFieldMessage(metadata);
}

function defaultBackendFieldMessage(metadata: SettingsFieldMetadata): string {
  if (metadata.value.kind === 'boolean') {
    return i18n.t('admin.validation.settingsBoolean', { label: metadata.label });
  }

  if (metadata.value.kind === 'integer' || metadata.value.kind === 'float') {
    return i18n.t('admin.validation.settingsRange', {
      label: metadata.label,
      min: metadata.value.min,
      max: metadata.value.max,
    });
  }

  return i18n.t('admin.settings.saveValidationError');
}

function extractBackendValidationEntries(payload: unknown): Array<{ path: string[]; message: string | null }> {
  if (!payload || typeof payload !== 'object') {
    return [];
  }

  const detail = (payload as Record<string, unknown>).detail;
  const errors = (payload as Record<string, unknown>).errors;
  const candidates = Array.isArray(detail) ? detail : Array.isArray(errors) ? errors : [];

  return candidates
    .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === 'object')
    .map((entry) => ({
      path: Array.isArray(entry.loc) ? entry.loc.filter((segment): segment is string => typeof segment === 'string') : [],
      message:
        (typeof entry.msg === 'string' && entry.msg.trim() ? entry.msg : null) ??
        (typeof entry.message === 'string' && entry.message.trim() ? entry.message : null) ??
        (typeof entry.detail === 'string' && entry.detail.trim() ? entry.detail : null),
    }));
}

function localizeBackendMessage(message: string | null): string | null {
  if (!message) {
    return null;
  }

  if (/[Р-пр-џЈИ]/.test(message)) {
    return message;
  }

  return null;
}

