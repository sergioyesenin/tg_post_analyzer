import type { PropsWithChildren } from 'react';
import { createContext, useContext, useEffect, useState } from 'react';

import { apiClient } from '@shared/api/client';
import type { SessionStatus, SessionUser } from '@shared/auth/session-types';

type SessionContextValue = {
  status: SessionStatus;
  user: SessionUser | null;
  signOut: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export type SessionBootstrap = () => Promise<SessionUser | null>;

type SessionProviderProps = PropsWithChildren<{
  bootstrap?: SessionBootstrap;
}>;

async function defaultSessionBootstrap() {
  try {
    return await apiClient.get<SessionUser>('/api/auth/me');
  } catch {
    return null;
  }
}

export function SessionProvider({ children, bootstrap = defaultSessionBootstrap }: SessionProviderProps) {
  const [status, setStatus] = useState<SessionStatus>('bootstrapping');
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    let cancelled = false;

    const bootstrapSession = async () => {
      const currentUser = await bootstrap();

      if (!cancelled) {
        if (currentUser) {
          setUser(currentUser);
          setStatus('authenticated');
        } else {
          setUser(null);
          setStatus('guest');
        }
      }
    };

    void bootstrapSession();

    return () => {
      cancelled = true;
    };
  }, [bootstrap]);

  const value: SessionContextValue = {
    status,
    user,
    signOut: () => {
      setUser(null);
      setStatus('guest');
    },
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);

  if (!context) {
    throw new Error('useSession must be used within SessionProvider.');
  }

  return context;
}
