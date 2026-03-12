import type { PropsWithChildren } from 'react';
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { authApi, type AuthApiContract } from '@shared/auth/auth-api';
import { getPrimaryRole, hasRequiredRole, normalizeRoles } from '@shared/auth/roles';
import type {
  LoginCredentials,
  SessionStatus,
  SessionTokens,
  SessionUser,
} from '@shared/auth/session-types';
import { tokenStorage, type TokenStorage } from '@shared/auth/token-storage';
import { apiClient } from '@shared/api/client';

type SessionContextValue = {
  status: SessionStatus;
  user: SessionUser | null;
  tokens: SessionTokens | null;
  primaryRole: ReturnType<typeof getPrimaryRole>;
  bootstrap: () => Promise<void>;
  login: (credentials: LoginCredentials) => Promise<SessionUser>;
  logout: () => Promise<void>;
  hasAnyRole: (roles: readonly string[]) => boolean;
};

type SessionProviderProps = PropsWithChildren<{
  authApi?: AuthApiContract;
  storage?: TokenStorage;
}>;

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  children,
  authApi: authApiInstance = authApi,
  storage = tokenStorage,
}: SessionProviderProps) {
  const [status, setStatus] = useState<SessionStatus>('bootstrapping');
  const [user, setUser] = useState<SessionUser | null>(null);
  const [tokens, setTokens] = useState<SessionTokens | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);
  const tokensRef = useRef<SessionTokens | null>(null);

  const clearSession = () => {
    tokensRef.current = null;
    setTokens(null);
    setUser(null);
    setStatus('guest');
    storage.clear();
  };

  const storeTokens = (nextTokens: SessionTokens) => {
    tokensRef.current = nextTokens;
    setTokens(nextTokens);
    storage.save(nextTokens);
  };

  const refreshAccessToken = async () => {
    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current;
    }

    const currentTokens = tokensRef.current;
    if (!currentTokens?.refreshToken) {
      clearSession();
      return null;
    }

    refreshPromiseRef.current = authApiInstance
      .refresh(currentTokens.refreshToken)
      .then(({ tokens: refreshedTokens }) => {
        storeTokens(refreshedTokens);
        return refreshedTokens.accessToken;
      })
      .catch(() => {
        clearSession();
        return null;
      })
      .finally(() => {
        refreshPromiseRef.current = null;
      });

    return refreshPromiseRef.current;
  };

  useEffect(() => {
    apiClient.configureAuth({
      getAccessToken: () => tokensRef.current?.accessToken ?? null,
      refreshAccessToken,
      onUnauthorized: clearSession,
    });
  });

  const bootstrap = async () => {
    setStatus('bootstrapping');
    const persistedTokens = storage.load();

    if (!persistedTokens) {
      clearSession();
      return;
    }

    storeTokens(persistedTokens);

    try {
      const currentUser = await authApiInstance.me();
      setUser({
        ...currentUser,
        roles: normalizeRoles(currentUser.roles),
      });
      setStatus('authenticated');
    } catch {
      clearSession();
    }
  };

  useEffect(() => {
    void bootstrap();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    const { tokens: nextTokens } = await authApiInstance.login(credentials);
    storeTokens(nextTokens);

    const currentUser = await authApiInstance.me();
    setUser({
      ...currentUser,
      roles: normalizeRoles(currentUser.roles),
    });
    setStatus('authenticated');
    return currentUser;
  };

  const logout = async () => {
    const refreshToken = tokensRef.current?.refreshToken;

    try {
      if (refreshToken) {
        await authApiInstance.logout(refreshToken);
      }
    } catch {
      // Logout should still clear local session when backend revoke fails.
    } finally {
      clearSession();
    }
  };

  const value = useMemo<SessionContextValue>(
    () => ({
      status,
      user,
      tokens,
      primaryRole: getPrimaryRole(user?.roles ?? []),
      bootstrap,
      login,
      logout,
      hasAnyRole: (roles) => hasRequiredRole(user?.roles ?? [], normalizeRoles([...roles])),
    }),
    [status, user, tokens],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);

  if (!context) {
    throw new Error('useSession must be used within SessionProvider.');
  }

  return context;
}
