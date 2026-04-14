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

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

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
        return null;
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
      expect(screen.getByRole('heading', { name: ru('\u041f\u043e\u0441\u0442 #42') })).toBeInTheDocument();
    });

    expect(screen.getByText(/Detailed post body for the post detail screen/i)).toBeInTheDocument();
    expect(screen.getByText(ru('\u0033 \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0435\u0432'))).toBeInTheDocument();
    expect(screen.getByText(/14\s?300 \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u043e\u0432/i)).toBeInTheDocument();
  });

  it('loads comments, links, and report blocks', async () => {
    installDetailGetMock();

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText(/Top-level comment/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Nested reply with thread metadata/i)).toBeInTheDocument();
    expect(screen.getByText(ru('\u0441 \u0443\u0447\u0435\u0442\u043e\u043c \u0442\u0440\u0435\u0434\u0430'))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u0432\u044f\u0437\u0430\u043d\u043d\u044b\u0439 \u043f\u043e\u0441\u0442') })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043e\u0442\u0447\u0435\u0442') })).toBeInTheDocument();
    expect(screen.getByText(/Report content body/i)).toBeInTheDocument();
  });

  it('renders limited public report semantics without needing internal traces', async () => {
    installDetailGetMock({
      report: createReportResponse({
        status: 'limited',
        content: 'Limited report body.',
        report_json: {
          summary: 'Анализ ограничен: проанализировано 8 комментариев; преобладает нейтральный тон.',
          topics: [{ name: 'бюджет' }, { name: 'регионы' }],
        },
      }),
    });

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText(/Limited report body/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Статус отчета: Ограничен/i)).toBeInTheDocument();
    expect(screen.getByText(/Анализ ограничен:/i)).toBeInTheDocument();
    expect(screen.getByText(/Темы: бюджет, регионы/i)).toBeInTheDocument();
  });

  it('renders insufficient-data public report semantics as a normal detail state', async () => {
    installDetailGetMock({
      report: createReportResponse({
        status: 'insufficient_data',
        content: 'Insufficient-data report body.',
        report_json: {
          summary: 'Недостаточно данных для надежного вывода: проанализировано 2 комментария.',
          topics: [],
        },
      }),
    });

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText(/Insufficient-data report body/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Статус отчета: Недостаточно данных/i)).toBeInTheDocument();
    expect(screen.getByText(/Недостаточно данных для надежного вывода/i)).toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0435\u0432'))).toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u0430'))).toBeInTheDocument();
      expect(screen.getByText(/report_id: 15/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Newly generated draft report/i)).toBeInTheDocument();
    });
  });

  it('shows building_report and completes report update from websocket progress', async () => {
    const user = userEvent.setup();
    let reportVersion = 0;
    const originalWebSocket = globalThis.WebSocket;

    class FakeWebSocket {
      static instances: FakeWebSocket[] = [];
      url: string;
      onmessage: ((event: { data: string }) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        FakeWebSocket.instances.push(this);
      }

      emit(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) });
      }

      close() {
        return undefined;
      }
    }

    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;

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
              content: 'WebSocket completed draft report.',
            });
      }

      if (path === '/api/posts/42/links') {
        return createLinksResponse();
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ status: 'running', type: 'build_post_report' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'running', job_id: 501 });
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
      expect(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u041e\u0442\u0447\u0435\u0442 \u0444\u043e\u0440\u043c\u0438\u0440\u0443\u0435\u0442\u0441\u044f'))).toBeInTheDocument();
    });

    expect(FakeWebSocket.instances[0]?.url).toContain('/api/reports/progress/ws');

    reportVersion = 1;
    FakeWebSocket.instances[0]?.emit({
      type: 'report_build_completed',
      entity_type: 'post',
      entity_id: 42,
      request_id: 501,
      status: 'completed',
      timestamp: '2026-04-09T12:00:00Z',
      result: { report_id: 15 },
    });

    await waitFor(() => {
      expect(screen.getByText(/report_id: 15/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/WebSocket completed draft report/i)).toBeInTheDocument();
    });

    globalThis.WebSocket = originalWebSocket;
  });
  it('hides mutation actions for viewer', async () => {
    installDetailGetMock();

    renderPostDetail('/posts/42', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0414\u043b\u044f viewer \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u043c\u0443\u0442\u0430\u0446\u0438\u0438 \u043f\u043e\u0441\u0442\u0430'))).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') })).not.toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') }));

    await waitFor(() => {
      expect(screen.getByText(/worker_failed/i)).toBeInTheDocument();
    });
  });
});



