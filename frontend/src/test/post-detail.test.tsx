import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createCommentsResponse,
  createJobResultResponse,
  createJobStatusResponse,
  createLinksResponse,
  createPostDetailResponse,
  createPostsDashboardResponse,
  createReportResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthApiMock(roles: string[] = ['analyst']) {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 31,
      username: roles[0],
      email: `${roles[0]}@example.com`,
      fullName: roles[0],
      isActive: true,
      isLocal: true,
      roles,
      createdAt: '2026-03-13T00:00:00Z',
    }),
    refresh: vi.fn(),
  } as never;
}

function renderPostDetail(initialEntry = '/posts/42', roles: string[] = ['analyst']) {
  return renderAuthHarness({
    authApi: createAuthApiMock(roles),
    storage: createMemoryTokenStorage({
      accessToken: 'token',
      refreshToken: 'refresh',
      expiresInSeconds: 3600,
    }),
    initialEntry,
  });
}

function installDetailGetMock(options?: {
  comments?: ReturnType<typeof createCommentsResponse>;
  report?: ReturnType<typeof createReportResponse> | null;
  links?: ReturnType<typeof createLinksResponse>;
  post?: ReturnType<typeof createPostDetailResponse>;
  dashboard?: ReturnType<typeof createPostsDashboardResponse>;
  jobStatus?: ReturnType<typeof createJobStatusResponse>;
  jobResult?: ReturnType<typeof createJobResultResponse>;
}) {
  const comments = options?.comments ?? createCommentsResponse();
  const report = options?.report ?? createReportResponse();
  const links = options?.links ?? createLinksResponse();
  const post = options?.post ?? createPostDetailResponse();
  const dashboard = options?.dashboard ?? createPostsDashboardResponse();
  const jobStatus = options?.jobStatus ?? createJobStatusResponse();
  const jobResult = options?.jobResult ?? createJobResultResponse();

  return vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
    if (path === '/api/posts/42') {
      return post;
    }

    if (path === '/api/posts/42/comments') {
      return comments;
    }

    if (path === '/api/reports/post/42') {
      if (report === null) {
        throw Object.assign(new Error('Not found'), { status: 404, name: 'ApiError' });
      }

      return report;
    }

    if (path === '/api/posts/42/links') {
      return links;
    }

    if (path === '/api/jobs/501') {
      return jobStatus;
    }

    if (path === '/api/jobs/501/result') {
      return jobResult;
    }

    if (path.startsWith('/api/dashboard/posts')) {
      return dashboard;
    }

    throw new Error(`Unhandled GET path in test: ${path}`);
  });
}

describe('Post detail screen', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('loads post detail data and renders the detail layout', async () => {
    installDetailGetMock();

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Post #42/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/Detailed post body for the post detail screen/i)).toBeInTheDocument();
    expect(screen.getByText(/3 comments/i)).toBeInTheDocument();
    expect(screen.getByText(/14,300 views/i)).toBeInTheDocument();
  });

  it('loads comments, links, and report blocks', async () => {
    installDetailGetMock();

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText(/Top-level comment/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Nested reply with thread metadata/i)).toBeInTheDocument();
    expect(screen.getByText(/thread-aware/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open linked post/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Update report/i })).toBeInTheDocument();
    expect(screen.getByText(/Report content body/i)).toBeInTheDocument();
  });

  it('runs refresh comments async job flow and invalidates detail queries', async () => {
    const user = userEvent.setup();
    let commentsVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/posts/42') {
        return createPostDetailResponse({ comments_count: commentsVersion === 0 ? 2 : 4 });
      }

      if (path === '/api/posts/42/comments') {
        return commentsVersion === 0
          ? createCommentsResponse([{ ...createCommentsResponse()[0] }])
          : createCommentsResponse([
              ...createCommentsResponse(),
              {
                id: 3,
                post_id: 42,
                tg_message_id: 5003,
                parent_tg_message_id: null,
                parent_comment_id: null,
                thread_root_tg_message_id: null,
                depth: 0,
                text: 'Freshly loaded comment',
                date: '2026-03-12T11:15:00Z',
              },
            ]);
      }

      if (path === '/api/reports/post/42') {
        return createReportResponse();
      }

      if (path === '/api/posts/42/links') {
        return createLinksResponse();
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ status: 'done', type: 'refresh_comments' });
      }

      if (path === '/api/jobs/501/result') {
        commentsVersion = 1;
        return createJobResultResponse({ status: 'ok', job_id: 501, comments_saved: 4 });
      }

      if (path.startsWith('/api/dashboard/posts')) {
        return createPostsDashboardResponse();
      }

      throw new Error(`Unhandled GET path in test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'refresh_comments' }),
    );

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Refresh comments/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Refresh comments/i }));

    await waitFor(() => {
      expect(screen.getByText(/Comments refresh job/i)).toBeInTheDocument();
      expect(screen.getByText(/comments_saved: 4/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Freshly loaded comment/i)).toBeInTheDocument();
    });
  });

  it('runs generate or update report async job flow and renders final result', async () => {
    const user = userEvent.setup();
    let reportVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/posts/42') {
        return createPostDetailResponse();
      }

      if (path === '/api/posts/42/comments') {
        return createCommentsResponse();
      }

      if (path === '/api/reports/post/42') {
        return reportVersion === 0
          ? null
          : createReportResponse({
              id: 15,
              status: 'draft',
              content: 'Newly generated draft report.',
            });
      }

      if (path === '/api/posts/42/links') {
        return createLinksResponse();
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ status: 'done', type: 'build_post_report' });
      }

      if (path === '/api/jobs/501/result') {
        reportVersion = 1;
        return createJobResultResponse({ status: 'draft', post_id: 42, report_id: 15 });
      }

      if (path.startsWith('/api/dashboard/posts')) {
        return createPostsDashboardResponse();
      }

      throw new Error(`Unhandled GET path in test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_post_report' }),
    );

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Generate report/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Generate report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Report job/i)).toBeInTheDocument();
      expect(screen.getByText(/report_id: 15/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Newly generated draft report/i)).toBeInTheDocument();
    });
  });

  it('hides mutation actions for viewer', async () => {
    installDetailGetMock();

    renderPostDetail('/posts/42', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Viewer access has no post mutations/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /Refresh comments/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Generate report/i })).not.toBeInTheDocument();
  });

  it('renders failed job result for async actions', async () => {
    const user = userEvent.setup();
    installDetailGetMock({
      jobStatus: createJobStatusResponse({ status: 'failed', last_error: 'worker_failed' }),
      jobResult: createJobResultResponse({ status: 'failed', job_id: 501, error: 'worker_failed' }),
    });
    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'refresh_comments' }),
    );

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Refresh comments/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Refresh comments/i }));

    await waitFor(() => {
      expect(screen.getByText(/worker_failed/i)).toBeInTheDocument();
    });
  });
});
