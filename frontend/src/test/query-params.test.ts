import { describe, expect, it } from 'vitest';

import {
  getModeSwitchSearch,
  parseDashboardFilters,
  serializeDashboardFilters,
} from '@shared/dashboard/filters';
import { parseQueryParams, serializeQueryParams } from '@shared/utils/queryParams';

describe('Query param utilities', () => {
  it('parses repeated keys into arrays and keeps single values as strings', () => {
    expect(parseQueryParams('?mode=posts&channel_ids=1&channel_ids=4&sort_by=date')).toEqual({
      mode: 'posts',
      channel_ids: ['1', '4'],
      sort_by: 'date',
    });
  });

  it('serializes scalars and arrays while omitting empty values', () => {
    expect(
      serializeQueryParams({
        mode: 'events',
        channel_ids: [5, 9],
        empty: '',
        nullable: null,
        ignored: undefined,
        partial: true,
      }),
    ).toBe('mode=events&channel_ids=5&channel_ids=9&partial=true');
  });
});

describe('Dashboard filter parsing and serialization', () => {
  it('parses posts filters from URL and restores typed arrays', () => {
    expect(
      parseDashboardFilters(
        'posts',
        '?date_from=2026-03-01&date_to=2026-03-10&channel_ids=3,9&categories=media&report_status=ready&min_comments=12&sort_by=views&sort_order=asc',
      ),
    ).toEqual({
      date_from: '2026-03-01',
      date_to: '2026-03-10',
      limit: 25,
      channel_ids: [3, 9],
      categories: ['media'],
      min_comments: 12,
      report_status: ['ready'],
      sort_by: 'views',
      sort_order: 'asc',
    });
  });

  it('serializes only non-default dashboard filters into URL', () => {
    expect(
      serializeDashboardFilters('events', {
        date_from: '2026-03-01',
        date_to: null,
        limit: 25,
        status: ['active', 'cooling'],
        channel_ids: [7, 9],
        categories: ['media'],
        min_comments: null,
        sort_by: 'started_at',
        sort_order: 'asc',
      }),
    ).toBe('date_from=2026-03-01&status=active%2Ccooling&channel_ids=7%2C9&categories=media&sort_order=asc');
  });

  it('keeps only target-supported shared filters when switching dashboard modes', () => {
    expect(
      getModeSwitchSearch(
        'events',
        'processes',
        '?date_from=2026-03-01&channel_ids=7&status=active&sort_by=posts_count&sort_order=asc',
      ),
    ).toBe('?date_from=2026-03-01&sort_order=asc');
  });
});
