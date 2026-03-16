import type {
  EventGraphResponse,
  EventsDashboardResponse,
  PostsDashboardResponse,
  ProcessGraphResponse,
  ProcessesDashboardResponse,
} from '@shared/dashboard/contracts';
import type {
  CommentDto,
  LinkDto,
  PostDetailDto,
  PostLinksDto,
  ReportDto,
} from '@modules/workspace/post-detail/contracts';
import type { EventDetailDto } from '@modules/workspace/event-detail/contracts';
import type { ProcessDetailDto } from '@modules/workspace/process-detail/contracts';
import type { EventReportListItemDto, PostReportListItemDto, ProcessReportListItemDto } from '@modules/reports/contracts';
import type { AdminUserDto, AppSettingDto, ChannelDto } from '@modules/admin/contracts';
import type { DeadLetterJobDto, JobsSummaryDto, MonitorFullDto, PendingJobDto } from '@modules/platform/contracts';
import type {
  KeywordGraphBuildResponseDto,
  KeywordGraphReportResponseDto,
  KeywordSearchResponseDto,
} from '@modules/keyword-graph/contracts';
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

export function createEventDetailResponse(overrides: Partial<EventDetailDto> = {}): EventDetailDto {
  return {
    event: {
      id: 81,
      title: 'Election coverage spike',
      status: 'active',
      started_at: '2026-03-12T06:30:00Z',
      ended_at: null,
      confidence: 0.88,
      created_by: 'pipeline',
      comments_count: 310,
      involvement: 0.57,
      ...(overrides.event ?? {}),
    },
    post_ids: overrides.post_ids ?? [4012, 3975, 3980],
    root_post_id: overrides.root_post_id ?? 4012,
    channels: overrides.channels ?? ['signal_watch', 'briefing_room'],
  };
}

export function createProcessesDashboardResponse(
  overrides: Partial<ProcessesDashboardResponse> = {},
): ProcessesDashboardResponse {
  return {
    mode: 'processes',
    generated_at: '2026-03-13T08:45:00Z',
    partial: false,
    warnings: [],
    filters_applied: {
      date_from: null,
      date_to: null,
      limit: 25,
      status: [],
      min_comments: null,
      sort_by: 'started_at',
      sort_order: 'desc',
    },
    summary: {
      processes_count: 2,
      total_events: 5,
      total_comments: 1240,
      avg_involvement: 0.44,
      draft_reports: 1,
      failed_reports: 0,
    },
    items: [
      {
        process_id: 201,
        title: 'Narrative escalation chain',
        status: 'active',
        started_at: '2026-03-09T08:00:00Z',
        ended_at: null,
        confidence: 0.84,
        comments_count: 720,
        involvement: 0.51,
        events_count: 3,
        event_ids: [81, 82, 83],
        report_status: 'draft',
        graph_ready: true,
      },
      {
        process_id: 202,
        title: 'Cleanup response cycle',
        status: 'cooling',
        started_at: '2026-03-08T10:30:00Z',
        ended_at: '2026-03-10T18:00:00Z',
        confidence: 0.71,
        comments_count: 520,
        involvement: 0.32,
        events_count: 2,
        event_ids: [91, 92],
        report_status: 'ready',
        graph_ready: true,
      },
    ],
    meta: {
      sort: { by: 'started_at', order: 'desc' },
      supported_sorts: ['started_at', 'comments_count', 'involvement', 'events_count'],
    },
    ...overrides,
  };
}

export function createProcessGraphResponse(
  overrides: Partial<ProcessGraphResponse> = {},
): ProcessGraphResponse {
  return {
    summary: {
      process_id: 201,
      title: 'Narrative escalation chain',
      status: 'active',
      started_at: '2026-03-09T08:00:00Z',
      ended_at: null,
      confidence: 0.84,
      report_status: 'draft',
      events_count: 3,
      posts_count: 4,
      comments_count: 720,
      involvement: 0.51,
    },
    events: [
      {
        event_id: 81,
        title: 'Election coverage spike',
        status: 'active',
        started_at: '2026-03-12T06:30:00Z',
        ended_at: null,
        confidence: 0.88,
        relation_type: 'trigger',
        direction: 'src_to_dst',
        score: 0.82,
        post_ids: [4012, 3975],
      },
      {
        event_id: 82,
        title: 'Official response cascade',
        status: 'cooling',
        started_at: '2026-03-11T14:00:00Z',
        ended_at: '2026-03-12T02:30:00Z',
        confidence: 0.73,
        relation_type: 'response',
        direction: 'src_to_dst',
        score: 0.76,
        post_ids: [4100],
      },
    ],
    nodes: [
      {
        post_id: 4012,
        channel_id: 77,
        channel_username: 'signal_watch',
        date: '2026-03-12T06:45:00Z',
        text_preview: 'Root post anchors the first process event.',
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
        text_preview: 'Supporting post extends the same event.',
        comments_count: 83,
        views: 9800,
        involvement: 0.38,
        is_root: false,
      },
      {
        post_id: 4100,
        channel_id: 22,
        channel_username: 'gov_updates',
        date: '2026-03-11T14:05:00Z',
        text_preview: 'Official statement bridges into the next event.',
        comments_count: 190,
        views: 20100,
        involvement: 0.41,
        is_root: true,
      },
    ],
    edges: [
      {
        link_id: 33,
        src_post_id: 4012,
        dst_post_id: 3975,
        link_type: 'related',
        direction: 'src_to_dst',
        score: 0.81,
        status: 'verified',
      },
      {
        link_id: 34,
        src_post_id: 3975,
        dst_post_id: 4100,
        link_type: 'update',
        direction: 'src_to_dst',
        score: 0.69,
        status: 'verified',
      },
    ],
    mapping: {
      process_id: 201,
      event_to_post_ids: {
        81: [4012, 3975],
        82: [4100],
      },
    },
    ...overrides,
  };
}

export function createProcessDetailResponse(
  overrides: Partial<ProcessDetailDto> = {},
): ProcessDetailDto {
  return {
    process: {
      id: 201,
      title: 'Narrative escalation chain',
      status: 'active',
      started_at: '2026-03-09T08:00:00Z',
      ended_at: null,
      confidence: 0.84,
      created_by: 'analyst.bot',
      comments_count: 720,
      involvement: 0.51,
    },
    events: [
      {
        event_id: 81,
        title: 'Election coverage spike',
        started_at: '2026-03-12T06:30:00Z',
        ended_at: null,
        confidence: 0.88,
        relation_type: 'trigger',
        direction: 'src_to_dst',
        score: 0.82,
        status: 'active',
        post_ids: [4012, 3975],
      },
      {
        event_id: 82,
        title: 'Official response cascade',
        started_at: '2026-03-11T14:00:00Z',
        ended_at: '2026-03-12T02:30:00Z',
        confidence: 0.73,
        relation_type: 'response',
        direction: 'src_to_dst',
        score: 0.76,
        status: 'cooling',
        post_ids: [4100],
      },
    ],
    ...overrides,
  };
}

export function createPostReportsListResponse(overrides: PostReportListItemDto[] = []): PostReportListItemDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      report_id: 601,
      post_id: 4012,
      status: 'ready',
      created_at: '2026-03-13T08:45:00Z',
      post_date: '2026-03-12T10:10:00Z',
      channel_id: 77,
      channel_username: 'signal_watch',
      channel_category: 'media',
    },
    {
      report_id: 602,
      post_id: 3975,
      status: 'draft',
      created_at: '2026-03-13T07:00:00Z',
      post_date: '2026-03-11T18:55:00Z',
      channel_id: 91,
      channel_username: 'briefing_room',
      channel_category: 'official',
    },
  ];
}

export function createEventReportsListResponse(overrides: EventReportListItemDto[] = []): EventReportListItemDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      report_id: 701,
      event_id: 81,
      event_title: 'Election coverage spike',
      status: 'draft',
      version: 'v3',
      created_at: '2026-03-13T08:45:00Z',
    },
  ];
}

export function createProcessReportsListResponse(overrides: ProcessReportListItemDto[] = []): ProcessReportListItemDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      report_id: 801,
      process_id: 201,
      process_title: 'Narrative escalation chain',
      status: 'ready',
      version: 'v5',
      created_at: '2026-03-13T08:45:00Z',
    },
  ];
}

export function createChannelsResponse(overrides: ChannelDto[] = []): ChannelDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      id: 1,
      username: 'signal_watch',
      title: 'Signal Watch',
      category: 'media',
      is_active: true,
    },
    {
      id: 2,
      username: 'briefing_room',
      title: 'Briefing Room',
      category: 'official',
      is_active: false,
    },
  ];
}

export function createUsersResponse(overrides: AdminUserDto[] = []): AdminUserDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      full_name: 'Admin User',
      is_active: true,
      is_local: true,
      roles: ['admin'],
      created_at: '2026-03-13T08:45:00Z',
    },
    {
      id: 2,
      username: 'analyst',
      email: 'analyst@example.com',
      full_name: 'Analyst User',
      is_active: true,
      is_local: true,
      roles: ['analyst'],
      created_at: '2026-03-12T08:45:00Z',
    },
  ];
}

export function createSettingsResponse(overrides: AppSettingDto[] = []): AppSettingDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      key: 'jobs',
      value_json: {
        ai_poll_seconds: 30,
        ai_scheduler_limit: 20,
      },
      description: 'Jobs configuration',
      updated_by_user_id: 1,
      updated_at: '2026-03-13T08:45:00Z',
    },
    {
      key: 'ingest',
      value_json: {
        poll_seconds: 120,
        lookback_days: 7,
      },
      description: 'Ingest configuration',
      updated_by_user_id: 1,
      updated_at: '2026-03-13T07:45:00Z',
    },
  ];
}

export function createEffectiveSettingsResponse(overrides: Record<string, unknown> = {}) {
  return {
    jobs: {
      ai_poll_seconds: 30,
      ai_scheduler_limit: 20,
    },
    ingest: {
      poll_seconds: 120,
      lookback_days: 7,
    },
    ...overrides,
  };
}

export function createMonitorFullResponse(overrides: Partial<MonitorFullDto> = {}): MonitorFullDto {
  return {
    health: {
      status: 'degraded',
      time_utc: '2026-03-13T08:45:00Z',
      dependencies: {
        database: {
          ok: true,
          status: 'ok',
          latency_ms: 18.5,
          error: null,
        },
        telegram_client: {
          ok: false,
          connected: false,
          status: 'process_stale',
          last_heartbeat_at: '2026-03-13T08:00:00Z',
        },
        ai_pipeline: {
          ok: true,
          status: 'ok',
          last_heartbeat_at: '2026-03-13T08:44:00Z',
        },
        scheduler: {
          ok: true,
          enabled: true,
          status: 'warning',
          next_expected_run_at: '2026-03-14T00:00:00Z',
          last_enqueue_at: '2026-03-13T03:00:00Z',
          last_heartbeat_at: '2026-03-13T08:40:00Z',
        },
      },
    },
    system: {
      timestamp: '2026-03-13T08:45:00Z',
      host: {
        cpu_count: 8,
        pid: 1200,
      },
      cpu: {
        system_percent: 42.1,
        process_percent: 3.2,
      },
      memory: {
        total_bytes: 16000000000,
        available_bytes: 6000000000,
        used_bytes: 10000000000,
        used_percent: 62.5,
        process_rss_bytes: 300000000,
      },
      disk: {
        total_bytes: 100000000000,
        used_bytes: 55000000000,
        free_bytes: 45000000000,
        used_percent: 55,
      },
    },
    jobs: {
      total: 14,
      by_status: {
        pending: 4,
        running: 2,
        failed: 1,
        done: 7,
      },
      pending_lag_seconds: 180,
      retry_lag_seconds: 3600,
      dead_letter_count: 2,
    },
    pipeline: {
      ingest: {
        last_ingested_at: '2026-03-13T08:30:00Z',
        ingest_lag_seconds: 900,
        last_post_date: '2026-03-13T08:28:00Z',
        post_freshness_lag_seconds: 1020,
      },
      collect_comments: {
        window_since: '2026-03-13T07:45:00Z',
        error_pool_size: 4,
        flood_count: 1,
        rpc_count: 1,
        flood_rate: 0.25,
        rpc_rate: 0.25,
      },
      backlog: {
        jobs_created_1h: 12,
        jobs_done_1h: 9,
        delta_1h: 3,
      },
      archive: {
        retention_cutoff: '2026-02-12T08:45:00Z',
        oldest_unarchived_post_date: '2026-02-10T00:00:00Z',
        archive_lag_seconds: 7200,
        last_archive_job_at: '2026-03-13T03:00:00Z',
        archive_job_lag_seconds: 18000,
      },
      runtime: {
        telegram_pipeline: {
          runtime: 'telegram_pipeline',
          ok: false,
          status: 'process_stale',
          process: {
            status: 'stale',
            last_heartbeat_at: '2026-03-13T08:00:00Z',
            heartbeat_age_seconds: 2700,
            heartbeat_timeout_seconds: 120,
            pid: 1234,
          },
        },
        ai_pipeline: {
          runtime: 'ai_pipeline',
          ok: true,
          status: 'ok',
          process: {
            status: 'running',
            last_heartbeat_at: '2026-03-13T08:44:00Z',
            heartbeat_age_seconds: 60,
            heartbeat_timeout_seconds: 120,
            pid: 5678,
          },
        },
      },
    },
    scheduler: {
      status: 'warning',
      retention_mode: 'scheduler',
      enabled: true,
      timezone: 'Europe/Minsk',
      schedule: {
        retention_hour: 3,
        retention_minute: 0,
        last_expected_run_at: '2026-03-13T00:00:00Z',
        next_expected_run_at: '2026-03-14T00:00:00Z',
      },
      process: {
        status: 'running',
        last_heartbeat_at: '2026-03-13T08:40:00Z',
        heartbeat_age_seconds: 300,
        heartbeat_timeout_seconds: 120,
        pid: 999,
      },
      last_archive_enqueue_at: '2026-03-13T03:00:00Z',
      last_jobs_retention_enqueue_at: '2026-03-13T03:10:00Z',
      last_enqueue_at: '2026-03-13T03:10:00Z',
      enqueue_lag_seconds: 19800,
    },
    alerts: {
      status: 'critical',
      alerts_count: 2,
      alerts: [
        {
          severity: 'critical',
          metric: 'jobs.retry_lag_seconds',
          current: 3600,
          threshold: 1800,
          message: 'Retry lag is above threshold.',
        },
        {
          severity: 'warning',
          metric: 'telegram_pipeline.status',
          current: 'process_stale',
          threshold: 'ok',
          message: 'Telegram pipeline process is not healthy.',
        },
      ],
    },
    activity_24h: {
      since: '2026-03-12T08:45:00Z',
      posts_last_hours: 28,
      comments_last_hours: 412,
    },
    database: {
      database: 'tg_post_analyzer',
      bytes: 4096000000,
      pretty: '3906 MB',
    },
    ...overrides,
  };
}

export function createJobsSummaryResponse(overrides: Partial<JobsSummaryDto> = {}): JobsSummaryDto {
  return {
    total: 9,
    by_status: {
      pending: 3,
      running: 2,
      failed: 1,
      done: 3,
    },
    ...overrides,
  };
}

export function createPendingJobsResponse(overrides: PendingJobDto[] = []): PendingJobDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      id: 11,
      type: 'collect_comments',
      status: 'pending',
      priority: 50,
      run_at: '2026-03-13T08:45:00Z',
      retry_at: null,
      attempts: 0,
      max_attempts: 5,
      locked_by: null,
      last_error: null,
    },
    {
      id: 12,
      type: 'build_event_report',
      status: 'failed',
      priority: 40,
      run_at: '2026-03-13T08:15:00Z',
      retry_at: '2026-03-13T09:15:00Z',
      attempts: 3,
      max_attempts: 5,
      locked_by: null,
      last_error: 'worker_failed',
    },
  ];
}

export function createDeadLetterJobsResponse(overrides: DeadLetterJobDto[] = []): DeadLetterJobDto[] {
  if (overrides.length > 0) {
    return overrides;
  }

  return [
    {
      id: 91,
      source_job_id: 12,
      type: 'build_process_report',
      priority: 40,
      attempts: 5,
      max_attempts: 5,
      last_error: 'max_attempts_reached',
      failed_at: '2026-03-13T08:20:00Z',
    },
  ];
}

export function createKeywordSearchResponse(
  overrides: Partial<KeywordSearchResponseDto> = {},
): KeywordSearchResponseDto {
  return {
    query: 'policy shift',
    normalized_query: 'policy shift',
    lemmas: ['policy', 'shift'],
    took_ms: 142,
    total: 2,
    items: [
      {
        post_id: 4012,
        channel_id: 77,
        channel_username: 'signal_watch',
        date: '2026-03-12T10:10:00Z',
        text_preview: 'Policy shift discussion spikes across media channels.',
        comments_count: 328,
        views: 14300,
        involvement: 0.62,
        rank: 0.983,
        matched_lemmas: ['policy', 'shift'],
      },
      {
        post_id: 3975,
        channel_id: 91,
        channel_username: 'briefing_room',
        date: '2026-03-11T18:55:00Z',
        text_preview: 'Secondary mention confirms the same policy shift narrative.',
        comments_count: 209,
        views: 9800,
        involvement: 0.38,
        rank: 0.844,
        matched_lemmas: ['policy'],
      },
    ],
    ...overrides,
  };
}

export function createKeywordGraphBuildResponse(
  overrides: Partial<KeywordGraphBuildResponseDto> = {},
): KeywordGraphBuildResponseDto {
  return {
    seed_post_ids: [4012],
    excluded_post_ids: [],
    nodes: [
      {
        post_id: 4012,
        channel_id: 77,
        channel_username: 'signal_watch',
        date: '2026-03-12T10:10:00Z',
        text_preview: 'Policy shift discussion spikes across media channels.',
        comments_count: 328,
        views: 14300,
        involvement: 0.62,
        included_by: 'seed',
      },
      {
        post_id: 4100,
        channel_id: 22,
        channel_username: 'gov_updates',
        date: '2026-03-12T12:00:00Z',
        text_preview: 'Official clarification joins the same graph neighborhood.',
        comments_count: 120,
        views: 20100,
        involvement: 0.41,
        included_by: 'neighbors',
      },
    ],
    edges: [
      {
        link_id: 81,
        src_post_id: 4012,
        dst_post_id: 4100,
        link_type: 'related',
        direction: 'src_to_dst',
        score: 0.77,
        status: 'verified',
        edge_source: 'transient',
        evidence: {
          shared_lemmas: ['policy', 'clarification'],
        },
      },
    ],
    took_ms: 320,
    meta: {
      graph_mode: 'transient',
      include_neighbors: true,
    },
    ...overrides,
  };
}

export function createKeywordGraphReportResponse(
  overrides: Partial<KeywordGraphReportResponseDto> = {},
): KeywordGraphReportResponseDto {
  return {
    status: 'ready',
    title: 'Keyword graph report',
    post_ids: [4012],
    excluded_post_ids: [],
    content: 'Analytical report content for the keyword graph seed set.',
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

