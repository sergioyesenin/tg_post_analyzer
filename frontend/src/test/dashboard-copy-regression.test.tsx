import { readFileSync } from 'node:fs';
import { screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import { i18n } from '@shared/i18n/i18n';
import {
  createChannelsResponse,
  createPostsDashboardResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

const mojibakePattern = /[ÐÑÏÄ�]/;
const guardedFiles = [
  'src/shared/dashboard/search-availability.ts',
  'src/modules/workspace/posts/PostsDashboardScreen.tsx',
  'src/modules/workspace/events/EventsDashboardScreen.tsx',
  'src/modules/workspace/processes/ProcessesDashboardScreen.tsx',
  'src/shared/i18n/locales/ru/common.json',
  'src/shared/i18n/locales/en/common.json',
];

function createAuthApiMock() {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 21,
      username: 'analyst',
      email: 'analyst@example.com',
      fullName: 'Analyst',
      isActive: true,
      isLocal: true,
      roles: ['analyst'],
      createdAt: '2026-03-13T00:00:00Z',
    }),
    refresh: vi.fn(),
  } as never;
}

function cloneBundle(language: 'ru' | 'en') {
  return JSON.parse(JSON.stringify(i18n.getResourceBundle(language, 'common')));
}

function deletePath(target: Record<string, unknown>, dottedPath: string) {
  const segments = dottedPath.split('.');
  let cursor: Record<string, unknown> | undefined = target;

  for (let index = 0; index < segments.length - 1; index += 1) {
    const next = cursor?.[segments[index]];
    if (!next || typeof next !== 'object') {
      return;
    }
    cursor = next as Record<string, unknown>;
  }

  if (cursor) {
    delete cursor[segments.at(-1) as string];
  }
}

describe('dashboard analytical copy regression guard', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ru');
    vi.restoreAllMocks();
  });

  afterEach(async () => {
    await i18n.changeLanguage('ru');
  });

  it('keeps guarded analytical files free from mojibake markers', () => {
    for (const file of guardedFiles) {
      const content = readFileSync(file, 'utf8');
      expect(content, file).not.toMatch(mojibakePattern);
    }
  });

  it('shows readable fallback copy when dashboard translation keys are partially missing', async () => {
    const backupRu = cloneBundle('ru');
    const backupEn = cloneBundle('en');
    const missingKeys = [
      'posts.dashboard.keywordSearch.loadingTitle',
      'posts.dashboard.keywordSearch.loadingDescription',
    ];

    const ruBundle = cloneBundle('ru');
    const enBundle = cloneBundle('en');
    for (const key of missingKeys) {
      deletePath(ruBundle, key);
      deletePath(enBundle, key);
    }

    i18n.addResourceBundle('ru', 'common', ruBundle, true, true);
    i18n.addResourceBundle('en', 'common', enBundle, true, true);

    let resolveSearch: ((value: unknown) => void) | null = null;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }
      if (path.startsWith('/api/dashboard/posts')) {
        return createPostsDashboardResponse();
      }
      throw new Error(`Unhandled GET path in fallback regression test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockImplementation(async (path: string) => {
      if (path === '/api/keyword/search/posts') {
        return await new Promise((resolve) => {
          resolveSearch = resolve;
        });
      }
      throw new Error(`Unhandled POST path in fallback regression test: ${path}`);
    });

    try {
      renderAuthHarness({
        initialEntry: '/dashboard/posts?query=policy',
        storage: createMemoryTokenStorage({
          accessToken: 'access',
          refreshToken: 'refresh',
          expiresInSeconds: 3600,
        }),
        authApi: createAuthApiMock(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Ищем посты по запросу/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/Текущая таблица остается на экране, пока обновляются результаты поиска/i)).toBeInTheDocument();
      expect(screen.queryByText(mojibakePattern)).toBeNull();
    } finally {
      if (resolveSearch) {
        resolveSearch({ total: 0, items: [] });
      }
      i18n.addResourceBundle('ru', 'common', backupRu, true, true);
      i18n.addResourceBundle('en', 'common', backupEn, true, true);
    }
  });
});

