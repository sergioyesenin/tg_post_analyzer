import { describe, expect, it } from 'vitest';

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
