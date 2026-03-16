import type { UserRole } from '@shared/auth/roles';

export type SessionStatus = 'bootstrapping' | 'authenticated' | 'guest';

export type SessionTokens = {
  accessToken: string;
  expiresInSeconds: number;
};

export type SessionUser = {
  id: number;
  username: string;
  email: string | null;
  fullName: string | null;
  isActive: boolean;
  isLocal: boolean;
  roles: UserRole[];
  createdAt: string;
};

export type LoginCredentials = {
  username: string;
  password: string;
};

export type LoginState = 'idle' | 'loading' | 'invalid_credentials' | 'service_unavailable' | 'generic_error';
