import { z } from 'zod';

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

export type AddChannelFormValues = z.infer<typeof addChannelSchema>;
export type UpdateChannelFormValues = z.infer<typeof updateChannelSchema>;
export type CreateUserFormValues = z.infer<typeof createUserSchema>;
export type UpdateUserRolesFormValues = z.infer<typeof updateUserRolesSchema>;
export type UpdateSettingFormValues = z.infer<typeof updateSettingSchema>;
