import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createEventReportsListResponse,
  createJobResultResponse,
  createJobStatusResponse,
  createPostReportsListResponse,
  createProcessReportsListResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthenticatedUser(roles: string[]) {
  return {
    id: 11,
    username: roles[0],
    email: `${roles[0]}@example.com`,
    fullName: roles[0],
    isActive: true,
    isLocal: true,
    roles,
    createdAt: '2026-03-13T00:00:00Z',
  };
}

function createAuthApiMock(roles: string[]) {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue(createAuthenticatedUser(roles)),
    refresh: vi.fn(),
  } as never;
}

function renderReports(initialEntry = '/reports/posts', roles: string[] = ['analyst']) {
  return renderAuthHarness({
    authApi: createAuthApiMock(roles),
    storage: createMemoryTokenStorage({
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      expiresInSeconds: 3600,
    }),
    initialEntry,
  });
}

describe('Reports page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders reports list tables for posts, events, and processes', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        return createPostReportsListResponse();
      }

      if (path.startsWith('/api/reports/events/list')) {
        return createEventReportsListResponse();
      }

      if (path.startsWith('/api/reports/processes/list')) {
        return createProcessReportsListResponse();
      }

      throw new Error(`Unhandled GET path in reports rendering test: ${path}`);
    });

    const user = userEvent.setup();
    renderReports('/reports/posts');

    await waitFor(() => {
      expect(screen.getByText(/Post #4012/i)).toBeInTheDocument();
    });

    expect(screen.getAllByRole('link', { name: /Open post/i }).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('link', { name: /^Events$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Election coverage spike/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('link', { name: /^Processes$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Narrative escalation chain/i)).toBeInTheDocument();
    });
  });

  it('shows export actions to viewer while hiding batch generation controls', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        return createPostReportsListResponse();
      }

      throw new Error(`Unhandled GET path in reports role test: ${path}`);
    });

    renderReports('/reports/posts?channel_ids=77&limit=25', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Viewer access keeps report catalogs readable/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /Export CSV/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/reports/posts/export?channel_ids=77&limit=25&offset=0&format=csv'),
    );
    expect(screen.getByRole('link', { name: /Export JSON/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Generate by filter/i })).not.toBeInTheDocument();
  });

  it('runs batch report generation flow for post reports and refreshes the list', async () => {
    const user = userEvent.setup();
    let postsVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        postsVersion += 1;
        return createPostReportsListResponse(
          postsVersion > 1
            ? [
                {
                  ...createPostReportsListResponse()[0],
                  status: 'draft',
                },
              ]
            : createPostReportsListResponse(),
        );
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_post_report_batch', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'done', report_id: 601, post_id: 4012 });
      }

      throw new Error(`Unhandled GET path in reports batch test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_post_report_batch' }),
    );

    renderReports('/reports/posts?channel_ids=77&categories=media&min_comments=5&limit=25');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Generate by filter/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Generate by filter/i }));

    await waitFor(() => {
      expect(screen.getByText(/Batch report job/i)).toBeInTheDocument();
      expect(screen.getByText(/report_id: 601/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(/Draft/i).length).toBeGreaterThan(0);
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/reports/posts/generate-by-filter?channel_ids=77&categories=media&min_comments=5&limit=25&offset=0',
    );
  });

  it('renders empty and error states for reports catalogs', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/events/list')) {
        return [];
      }

      throw new Error(`Unhandled GET path in reports empty test: ${path}`);
    });

    renderReports('/reports/events');

    await waitFor(() => {
      expect(screen.getByText(/No event reports match the current filters/i)).toBeInTheDocument();
    });

    vi.restoreAllMocks();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/processes/list')) {
        throw new ApiError('Failed', 500);
      }

      throw new Error(`Unhandled GET path in reports error test: ${path}`);
    });

    renderReports('/reports/processes');

    await waitFor(() => {
      expect(screen.getByText(/Reports catalog failed to load/i)).toBeInTheDocument();
    });
  });
});
