import { AuthApiError } from '@shared/auth/auth-errors';
import { normalizeRoles } from '@shared/auth/roles';
import type { LoginCredentials, SessionTokens, SessionUser } from '@shared/auth/session-types';
import { apiClient, ApiClient, ApiError } from '@shared/api/client';

type TokenResponse = {
  access_token: string;
  refresh_token: string | null;
  expires_in_seconds: number;
  roles: string[];
  token_type: string;
};

type UserResponse = {
  id: number;
  username: string;
  email: string | null;
  full_name: string | null;
  is_active: boolean;
  is_local: boolean;
  roles: string[];
  created_at: string;
};

type LogoutResponse = {
  status: string;
  refresh_revoked: boolean;
};

type AuthApiDeps = {
  client?: ApiClient;
};

export interface AuthApiContract {
  login: (credentials: LoginCredentials) => Promise<{ tokens: SessionTokens; roles: ReturnType<typeof normalizeRoles> }>;
  refresh: () => Promise<{ tokens: SessionTokens; roles: ReturnType<typeof normalizeRoles> }>;
  logout: () => Promise<LogoutResponse>;
  me: () => Promise<SessionUser>;
}

function toSessionTokens(payload: TokenResponse): SessionTokens {
  return {
    accessToken: payload.access_token,
    expiresInSeconds: payload.expires_in_seconds,
  };
}

function toSessionUser(payload: UserResponse): SessionUser {
  return {
    id: payload.id,
    username: payload.username,
    email: payload.email,
    fullName: payload.full_name,
    isActive: payload.is_active,
    isLocal: payload.is_local,
    roles: normalizeRoles(payload.roles),
    createdAt: payload.created_at,
  };
}

export class AuthApi implements AuthApiContract {
  private readonly client: ApiClient;

  constructor(deps: AuthApiDeps = {}) {
    this.client = deps.client ?? apiClient;
  }

  async login(credentials: LoginCredentials) {
    try {
      const payload = await this.client.request<TokenResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(credentials),
        authMode: 'none',
        retryOnUnauthorized: false,
        credentials: 'include',
      });

      return {
        tokens: toSessionTokens(payload),
        roles: normalizeRoles(payload.roles),
      };
    } catch (error) {
      throw this.mapAuthError(error);
    }
  }

  async refresh() {
    try {
      const payload = await this.client.request<TokenResponse>('/api/auth/refresh', {
        method: 'POST',
        authMode: 'none',
        retryOnUnauthorized: false,
        credentials: 'include',
      });

      return {
        tokens: toSessionTokens(payload),
        roles: normalizeRoles(payload.roles),
      };
    } catch (error) {
      throw this.mapAuthError(error);
    }
  }

  async logout() {
    return this.client.request<LogoutResponse>('/api/auth/logout', {
      method: 'POST',
      retryOnUnauthorized: true,
      credentials: 'include',
    });
  }

  async me() {
    try {
      const payload = await this.client.get<UserResponse>('/api/auth/me');
      return toSessionUser(payload);
    } catch (error) {
      throw this.mapAuthError(error);
    }
  }

  private mapAuthError(error: unknown) {
    if (error instanceof AuthApiError) {
      return error;
    }

    if (error instanceof ApiError) {
      return new AuthApiError(error.message, error.status);
    }

    if (error instanceof Error) {
      return new AuthApiError(`Unexpected auth error: ${error.message}`, 500);
    }

    return new AuthApiError('Unexpected auth error', 500);
  }
}

export const authApi = new AuthApi();
