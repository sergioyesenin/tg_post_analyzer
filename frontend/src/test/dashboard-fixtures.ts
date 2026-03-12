import type { EventGraphResponse, EventsDashboardResponse, PostsDashboardResponse } from '@shared/dashboard/contracts';
import type {
  CommentDto,
  LinkDto,
  PostDetailDto,
  PostLinksDto,
  ReportDto,
} from '@modules/workspace/post-detail/contracts';
import type { AcceptedJobResponse, JobResultResponse, JobStatusResponse } from '@shared/jobs/contracts';

export function createPostsDashboardResponse(
  overrides: Partial<PostsDashboardResponse> = {},
): PostsDashboardResponse {
  return {
    mode: 'posts',
    generated_at: '2026-03-13T08:45:00Z',
    partial: false,
    warnings: [],
    filters_applied: {
      date_from: '',
      date_to: '',
      limit: 25,
      channel_ids: [],
      categories: [],
      min_comments: null,
      report_status: [],
      sort_by: 'date',
      sort_order: 'desc',
    },
    summary: {
      posts_count: 2,
      total_comments: 537,
      avg_involvement: 0.48,
      channels_count: 2,
      reports_ready: 1,
      reports_missing: 0,
      reports_pending: 1,
      reports_failed: 0,
    },
    items: [
      {
        post_id: 4012,
        channel_id: 77,
        channel_username: 'signal_watch',
        channel_title: 'Signal Watch',
        channel_category: 'media',
        date: '2026-03-12T10:10:00Z',
        text_preview: 'Top post preview for posts dashboard rendering.',
        comments_count: 328,
        views: 14300,
        involvement: 0.62,
        report_status: 'ready',
        has_report: true,
        comments_refresh_available: true,
        links_count: 12,
      },
      {
        post_id: 3975,
        channel_id: 91,
        channel_username: 'briefing_room',
        channel_title: 'Briefing Room',
        channel_category: 'official',
        date: '2026-03-11T18:55:00Z',
        text_preview: 'Secondary row validates dense table layout.',
        comments_count: 209,
        views: 9800,
        involvement: 0.38,
        report_status: 'pending',
        has_report: false,
        comments_refresh_available: true,
        links_count: 7,
      },
    ],
    meta: {
      sort: { by: 'date', order: 'desc' },
      supported_sorts: ['comments_count', 'date', 'views', 'involvement'],
    },
    ...overrides,
  };
}

export function createEventsDashboardResponse(
  overrides: Partial<EventsDashboardResponse> = {},
): EventsDashboardResponse {
  return {
    mode: 'events',
    generated_at: '2026-03-13T08:45:00Z',
    partial: false,
    warnings: [],
    filters_applied: {
      date_from: null,
      date_to: null,
      limit: 25,
      status: [],
      channel_ids: [],
      categories: [],
      min_comments: null,
      sort_by: 'started_at',
      sort_order: 'desc',
    },
    summary: {
      events_count: 2,
      total_linked_posts: 5,
      total_comments: 611,
      avg_involvement: 0.42,
      draft_reports: 1,
      ready_reports: 1,
      failed_reports: 0,
    },
    items: [
      {
        event_id: 81,
        title: 'Election coverage spike',
        status: 'active',
        started_at: '2026-03-12T06:30:00Z',
        ended_at: null,
        confidence: 0.88,
        comments_count: 310,
        involvement: 0.57,
        posts_count: 3,
        post_ids: [4012, 3975, 3980],
        root_post_id: 4012,
        channels: [
          { channel_id: 77, channel_username: 'signal_watch' },
          { channel_id: 91, channel_username: 'briefing_room' },
        ],
        report_status: 'draft',
        graph_ready: true,
      },
      {
        event_id: 82,
        title: 'Official response cascade',
        status: 'cooling',
        started_at: '2026-03-11T14:00:00Z',
        ended_at: '2026-03-12T02:30:00Z',
        confidence: 0.73,
        comments_count: 301,
        involvement: 0.35,
        posts_count: 2,
        post_ids: [4100, 4105],
        root_post_id: 4100,
        channels: [{ channel_id: 22, channel_username: 'gov_updates' }],
        report_status: 'ready',
        graph_ready: true,
      },
    ],
    meta: {
      sort: { by: 'started_at', order: 'desc' },
      supported_sorts: ['started_at', 'comments_count', 'involvement', 'posts_count'],
    },
    ...overrides,
  };
}

export function createEventGraphResponse(
  overrides: Partial<EventGraphResponse> = {},
): EventGraphResponse {
  return {
    event: {
      event_id: 81,
      title: 'Election coverage spike',
      status: 'active',
      started_at: '2026-03-12T06:30:00Z',
      ended_at: null,
      confidence: 0.88,
      report_status: 'draft',
      posts_count: 3,
      comments_count: 310,
      involvement: 0.57,
    },
    nodes: [
      {
        post_id: 4012,
        channel_id: 77,
        channel_username: 'signal_watch',
        date: '2026-03-12T06:45:00Z',
        text_preview: 'Root post drives the event graph.',
        comments_count: 170,
        views: 14300,
        involvement: 0.62,
        is_root: true,
      },
      {
        post_id: 3975,
        channel_id: 91,
        channel_username: 'briefing_room',
        date: '2026-03-12T07:10:00Z',
        text_preview: 'Linked post extends the same event narrative.',
        comments_count: 83,
        views: 9800,
        involvement: 0.38,
        is_root: false,
      },
    ],
    edges: [
      {
        link_id: 18,
        src_post_id: 4012,
        dst_post_id: 3975,
        link_type: 'related',
        direction: 'src_to_dst',
        score: 0.81,
        status: 'verified',
      },
    ],
    ...overrides,
  };
}

export function createPostDetailResponse(overrides: Partial<PostDetailDto> = {}): PostDetailDto {
  return {
    id: 42,
    channel_id: 7,
    text: 'Detailed post body for the post detail screen.',
    date: '2026-03-12T10:10:00Z',
    comments_count: 3,
    views: 14300,
    involvement: 0.62,
    ...overrides,
  };
}

export function createCommentsResponse(overrides: CommentDto[] = []): CommentDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      id: 1,
      post_id: 42,
      tg_message_id: 5001,
      parent_tg_message_id: null,
      parent_comment_id: null,
      thread_root_tg_message_id: null,
      depth: 0,
      text: 'Top-level comment',
      date: '2026-03-12T11:00:00Z',
    },
    {
      id: 2,
      post_id: 42,
      tg_message_id: 5002,
      parent_tg_message_id: 5001,
      parent_comment_id: 1,
      thread_root_tg_message_id: 5001,
      depth: 1,
      text: 'Nested reply with thread metadata',
      date: '2026-03-12T11:05:00Z',
    },
  ];
}

export function createReportResponse(overrides: Partial<ReportDto> = {}): ReportDto {
  return {
    id: 9,
    post_id: 42,
    status: 'ready',
    content: 'Report content body.',
    created_at: '2026-03-12T12:00:00Z',
    ...overrides,
  };
}

export function createLinksResponse(overrides: LinkDto[] = []): PostLinksDto {
  return {
    post_id: 42,
    links:
      overrides.length > 0
        ? overrides
        : [
            {
              id: 4,
              src_post_id: 42,
              dst_post_id: 84,
              link_type: 'update',
              direction: 'src_to_dst',
              score: 0.83,
              status: 'verified',
              evidence_json: null,
              model_version: 'v1',
              pipeline_version: 'p1',
              created_at: '2026-03-12T12:10:00Z',
              updated_at: '2026-03-12T12:15:00Z',
            },
          ],
  };
}

export function createAcceptedJobResponse(
  overrides: Partial<AcceptedJobResponse> = {},
): AcceptedJobResponse {
  return {
    status: 'queued',
    job_id: 501,
    job_type: 'refresh_comments',
    status_url: '/api/jobs/501',
    result_url: '/api/jobs/501/result',
    ...overrides,
  };
}

export function createJobStatusResponse(overrides: Partial<JobStatusResponse> = {}): JobStatusResponse {
  return {
    id: 501,
    type: 'refresh_comments',
    status: 'done',
    priority: 1,
    run_at: '2026-03-13T08:45:00Z',
    retry_at: null,
    attempts: 1,
    max_attempts: 5,
    locked_by: null,
    locked_at: null,
    heartbeat_at: null,
    last_error: null,
    created_at: '2026-03-13T08:45:00Z',
    updated_at: '2026-03-13T08:46:00Z',
    result_url: '/api/jobs/501/result',
    ...overrides,
  };
}

export function createJobResultResponse(
  overrides: JobResultResponse = { status: 'ok', job_id: 501, comments_saved: 4 },
): JobResultResponse {
  return overrides;
}
