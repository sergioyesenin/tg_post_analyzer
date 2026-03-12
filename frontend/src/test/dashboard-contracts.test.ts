import { describe, expect, it } from 'vitest';

import type { EventsDashboardResponse, PostsDashboardResponse } from '@shared/dashboard/contracts';
import { mapDashboardResponseToViewModel } from '@shared/dashboard/mappers';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';

describe('Dashboard contracts foundation', () => {
  it('keeps transport envelope separate from mapped view model entry point', () => {
    const response: PostsDashboardResponse = {
      mode: 'posts',
      generated_at: '2026-03-13T00:00:00Z',
      partial: false,
      warnings: [],
      filters_applied: {
        date_from: '2026-03-01T00:00:00Z',
        date_to: '2026-03-13T00:00:00Z',
        limit: 25,
        channel_ids: [1],
        categories: ['news'],
        min_comments: null,
        report_status: [],
        sort_by: 'date',
        sort_order: 'desc',
      },
      summary: {
        posts_count: 10,
        total_comments: 50,
        avg_involvement: 1.4,
        channels_count: 1,
        reports_ready: 5,
        reports_missing: 3,
        reports_pending: 1,
        reports_failed: 1,
      },
      items: [],
      meta: {
        sort: { by: 'date', order: 'desc' },
        supported_sorts: ['date'],
      },
    };

    expect(mapDashboardResponseToViewModel(response)).toEqual({
      transport: response,
      generatedAt: '2026-03-13T00:00:00Z',
      isPartial: false,
      warnings: [],
    });
  });

  it('defines stable query key conventions for mode and graph resources', () => {
    expect(dashboardQueryKeys.list('events', 'mode=events')).toEqual([
      'dashboard',
      'events',
      'list',
      'mode=events',
    ]);
    expect(dashboardQueryKeys.graph.event(17)).toEqual(['dashboard', 'event-graph', 17]);
  });

  it('supports partial dashboard payloads without treating warnings as hard errors', () => {
    const response: EventsDashboardResponse = {
      mode: 'events',
      generated_at: '2026-03-13T00:00:00Z',
      partial: true,
      warnings: [
        {
          code: 'events.graph.pending',
          message: 'Graph enrichment is not ready.',
          severity: 'warning',
        },
      ],
      filters_applied: {
        date_from: null,
        date_to: null,
        limit: 20,
        status: [],
        channel_ids: [],
        categories: [],
        min_comments: null,
        sort_by: 'started_at',
        sort_order: 'desc',
      },
      summary: {
        events_count: 3,
        total_linked_posts: 5,
        total_comments: 8,
        avg_involvement: 0.7,
        draft_reports: 1,
        ready_reports: 1,
        failed_reports: 0,
      },
      items: [],
      meta: {
        sort: { by: 'started_at', order: 'desc' },
        supported_sorts: ['started_at'],
      },
    };

    const viewModel = mapDashboardResponseToViewModel(response);
    expect(viewModel.isPartial).toBe(true);
    expect(viewModel.warnings).toHaveLength(1);
  });
});
