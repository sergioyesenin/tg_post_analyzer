import { z } from 'zod';

export const addChannelSchema = z.object({
  username: z.string().trim().min(1, 'Username is required'),
});

export const updateChannelSchema = z.object({
  title: z.string().trim().optional().or(z.literal('')),
  category: z.string().trim().optional().or(z.literal('')),
  is_active: z.boolean(),
});

export const createUserSchema = z.object({
  username: z.string().trim().min(1, 'Username is required'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  email: z.string().email('Email must be valid').optional().or(z.literal('')),
  full_name: z.string().optional().or(z.literal('')),
  roles: z.array(z.enum(['admin', 'analyst', 'viewer'])).min(1, 'At least one role is required'),
});

export const updateUserRolesSchema = z.object({
  roles: z.array(z.enum(['admin', 'analyst', 'viewer'])).min(1, 'At least one role is required'),
});

export const updateSettingSchema = z.object({
  description: z.string().optional().or(z.literal('')),
  value_json_text: z
    .string()
    .trim()
    .min(2, 'JSON payload is required')
    .refine((value) => {
      try {
        const parsed = JSON.parse(value);
        return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed);
      } catch {
        return false;
      }
    }, 'Value must be a valid JSON object'),
});

export type AddChannelFormValues = z.infer<typeof addChannelSchema>;
export type UpdateChannelFormValues = z.infer<typeof updateChannelSchema>;
export type CreateUserFormValues = z.infer<typeof createUserSchema>;
export type UpdateUserRolesFormValues = z.infer<typeof updateUserRolesSchema>;
export type UpdateSettingFormValues = z.infer<typeof updateSettingSchema>;
