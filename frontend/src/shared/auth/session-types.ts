import type { UserRole } from '@shared/auth/roles';

export type SessionStatus = 'bootstrapping' | 'authenticated' | 'guest';

export type SessionUser = {
  id: string;
  email: string;
  role: UserRole;
};
