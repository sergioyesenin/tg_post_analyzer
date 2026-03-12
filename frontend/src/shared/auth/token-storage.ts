import type { SessionTokens } from '@shared/auth/session-types';

const STORAGE_KEY = 'tgpa.session.tokens';

export type TokenStorage = {
  load: () => SessionTokens | null;
  save: (tokens: SessionTokens) => void;
  clear: () => void;
};

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

export const tokenStorage: TokenStorage = {
  load() {
    if (!canUseStorage()) {
      return null;
    }

    const rawValue = window.localStorage.getItem(STORAGE_KEY);
    if (!rawValue) {
      return null;
    }

    try {
      return JSON.parse(rawValue) as SessionTokens;
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
  },
  save(tokens) {
    if (!canUseStorage()) {
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  },
  clear() {
    if (!canUseStorage()) {
      return;
    }

    window.localStorage.removeItem(STORAGE_KEY);
  },
};
