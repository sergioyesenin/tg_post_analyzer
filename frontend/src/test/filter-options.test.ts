import { describe, expect, it } from 'vitest';

import { getEventsDashboardFilterOptions, getPostsDashboardFilterOptions } from '@shared/dashboard/filter-options';

describe('dashboard filter channel options', () => {
  it('falls back to selected ids when channels payload is not an array for posts', () => {
    const options = getPostsDashboardFilterOptions({
      filters: {
        query: '',
        date_from: '',
        date_to: '',
        limit: 25,
        channel_ids: [7],
        categories: [],
        min_comments: null,
        report_status: [],
        sort_by: 'date',
        sort_order: 'desc',
      },
      dashboardData: null,
      channels: { items: [] } as never,
    });

    expect(options.channel_ids).toEqual([
      {
        value: 7,
        label: 'Channel #7',
        description: '#7',
      },
    ]);
    expect(options.categories).toEqual([]);
  });

  it('ignores malformed channels payload for events instead of throwing', () => {
    expect(() =>
      getEventsDashboardFilterOptions({
        filters: {
          query: '',
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
        dashboardData: null,
        channels: { results: [] } as never,
      }),
    ).not.toThrow();
  });

  it('includes expanded public report statuses for posts', () => {
    const options = getPostsDashboardFilterOptions({
      filters: {
        query: '',
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
      dashboardData: null,
      channels: [],
    });

    expect(options.report_status.map((item) => item.value)).toEqual(
      expect.arrayContaining(['ready', 'limited', 'insufficient_data', 'failed']),
    );
  });
});
