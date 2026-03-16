import type { SessionTokens } from '@shared/auth/session-types';

export type TokenStorage = {
  load: () => SessionTokens | null;
  save: (tokens: SessionTokens) => void;
  clear: () => void;
};

let currentTokens: SessionTokens | null = null;

export const tokenStorage: TokenStorage = {
  load() {
    return currentTokens;
  },
  save(tokens) {
    currentTokens = tokens;
  },
  clear() {
    currentTokens = null;
  },
};
