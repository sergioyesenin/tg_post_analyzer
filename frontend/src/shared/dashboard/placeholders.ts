import type {
  DashboardMode,
  DashboardTransportResponse,
  EventsDashboardResponse,
  PostsDashboardResponse,
  ProcessesDashboardResponse,
} from '@shared/dashboard/contracts';
import type { DashboardFiltersByMode } from '@shared/dashboard/filters';

function isoNow() {
  return '2026-03-13T08:45:00Z';
}

export function buildDashboardPlaceholderResponse<TMode extends DashboardMode>(
  mode: TMode,
  filters: DashboardFiltersByMode[TMode],
): Extract<DashboardTransportResponse, { mode: TMode }> {
  if (mode === 'posts') {
    const response: PostsDashboardResponse = {
      mode,
      generated_at: isoNow(),
      partial: false,
      warnings: [],
      filters_applied: filters as PostsDashboardResponse['filters_applied'],
      summary: {
        posts_count: 182,
        total_comments: 4123,
        avg_involvement: 0.47,
        channels_count: 18,
        reports_ready: 96,
        reports_missing: 42,
        reports_pending: 31,
        reports_failed: 13,
      },
      items: [
        {
          post_id: 4012,
          channel_id: 77,
          channel_username: 'signal_watch',
          channel_title: 'Signal Watch',
          channel_category: 'media',
          date: '2026-03-12T10:10:00Z',
          text_preview: 'Top post preview for workspace shell validation.',
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
          text_preview: 'Secondary row keeps table shell and navigation working.',
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
        sort: { by: filters.sort_by, order: filters.sort_order },
        supported_sorts: ['comments_count', 'date', 'views', 'involvement'],
      },
    };

    return response as Extract<DashboardTransportResponse, { mode: TMode }>;
  }

  if (mode === 'events') {
    const response: EventsDashboardResponse = {
      mode,
      generated_at: isoNow(),
      partial: true,
      warnings: [
        {
          code: 'events.graph.pending',
          message: 'Graph enrichment is partially unavailable; table and summary remain usable.',
          severity: 'warning',
        },
      ],
      filters_applied: filters as EventsDashboardResponse['filters_applied'],
      summary: {
        events_count: 28,
        total_linked_posts: 241,
        total_comments: 3180,
        avg_involvement: 0.41,
        draft_reports: 7,
        ready_reports: 12,
        failed_reports: 2,
      },
      items: [
        {
          event_id: 510,
          title: 'Election coverage spike',
          status: 'active',
          started_at: '2026-03-10T07:00:00Z',
          ended_at: null,
          confidence: 0.88,
          comments_count: 920,
          involvement: 0.57,
          posts_count: 44,
          post_ids: [4012, 3975],
          root_post_id: 4012,
          channels: [{ channel_id: 77, channel_username: 'signal_watch' }],
          report_status: 'draft',
          graph_ready: false,
        },
      ],
      meta: {
        sort: { by: filters.sort_by, order: filters.sort_order },
        supported_sorts: ['started_at', 'comments_count', 'involvement', 'posts_count'],
      },
    };

    return response as Extract<DashboardTransportResponse, { mode: TMode }>;
  }

  const response: ProcessesDashboardResponse = {
    mode,
    generated_at: isoNow(),
    partial: true,
    warnings: [
      {
        code: 'processes.graph.snapshot_degraded',
        message: 'Process graph snapshot is incomplete, but the workspace remains navigable.',
        severity: 'warning',
      },
      {
        code: 'processes.related_events.pending',
        message: 'Related events enrichment is still loading in the backend snapshot.',
        severity: 'info',
      },
    ],
    filters_applied: filters as ProcessesDashboardResponse['filters_applied'],
    summary: {
      processes_count: 11,
      total_events: 39,
      total_comments: 2710,
      avg_involvement: 0.36,
      draft_reports: 3,
      failed_reports: 1,
    },
    items: [
      {
        process_id: 88,
        title: 'Narrative escalation chain',
        status: 'active',
        started_at: '2026-03-08T09:15:00Z',
        ended_at: null,
        confidence: 0.81,
        comments_count: 511,
        involvement: 0.42,
        events_count: 6,
        event_ids: [510, 511],
        post_ids: [4012, 3975],
        report_status: 'draft',
        graph_ready: false,
      },
    ],
    meta: {
      sort: { by: filters.sort_by, order: filters.sort_order },
      supported_sorts: ['started_at', 'comments_count', 'involvement', 'events_count'],
    },
  };

  return response as Extract<DashboardTransportResponse, { mode: TMode }>;
}

