import type {
  DashboardMode,
  EventsDashboardFiltersDto,
  PostsDashboardFiltersDto,
  ProcessesDashboardFiltersDto,
} from '@shared/dashboard/contracts';
import { serializeQueryParams } from '@shared/utils/queryParams';

type SortOrder = 'asc' | 'desc';

export type DashboardFiltersByMode = {
  posts: PostsDashboardFiltersDto;
  events: EventsDashboardFiltersDto;
  processes: ProcessesDashboardFiltersDto;
};

export type DashboardFilterKey = keyof DashboardFiltersByMode['posts'] | keyof DashboardFiltersByMode['events'];

type FilterConfig<TMode extends DashboardMode> = {
  defaults: DashboardFiltersByMode[TMode];
  allowedKeys: readonly DashboardFilterKey[];
  modeSwitchPreservedKeys: readonly DashboardFilterKey[];
  sortOptions: readonly string[];
};

const commonPreservedKeys = ['query', 'date_from', 'date_to', 'limit', 'min_comments', 'sort_order'] as const;

const filterConfigs: { [TMode in DashboardMode]: FilterConfig<TMode> } = {
  posts: {
    defaults: {
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
    allowedKeys: [
      'query',
      'date_from',
      'date_to',
      'limit',
      'channel_ids',
      'categories',
      'min_comments',
      'report_status',
      'sort_by',
      'sort_order',
    ],
    modeSwitchPreservedKeys: [...commonPreservedKeys, 'channel_ids', 'categories'],
    sortOptions: ['comments_count', 'date', 'views', 'involvement'],
  },
  events: {
    defaults: {
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
    allowedKeys: [
      'query',
      'date_from',
      'date_to',
      'limit',
      'status',
      'channel_ids',
      'categories',
      'min_comments',
      'sort_by',
      'sort_order',
    ],
    modeSwitchPreservedKeys: [...commonPreservedKeys, 'channel_ids', 'categories'],
    sortOptions: ['started_at', 'comments_count', 'involvement', 'posts_count'],
  },
  processes: {
    defaults: {
      query: '',
      date_from: null,
      date_to: null,
      limit: 25,
      status: [],
      min_comments: null,
      sort_by: 'started_at',
      sort_order: 'desc',
    },
    allowedKeys: ['query', 'date_from', 'date_to', 'limit', 'status', 'min_comments', 'sort_by', 'sort_order'],
    modeSwitchPreservedKeys: commonPreservedKeys,
    sortOptions: ['started_at', 'comments_count', 'involvement', 'events_count'],
  },
};

function parseStringList(params: URLSearchParams, key: string) {
  return params
    .getAll(key)
    .flatMap((value) => value.split(','))
    .map((value) => value.trim())
    .filter(Boolean);
}

function parseNumberList(params: URLSearchParams, key: string) {
  return params
    .getAll(key)
    .flatMap((value) => value.split(','))
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
}

function parseNumber(params: URLSearchParams, key: string, fallback: number | null) {
  const rawValue = params.get(key);

  if (!rawValue) {
    return fallback;
  }

  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseNullableDate(params: URLSearchParams, key: 'date_from' | 'date_to', fallback: string | null) {
  const rawValue = params.get(key);
  return rawValue && rawValue.trim() ? rawValue : fallback;
}

function parseQueryValue(params: URLSearchParams) {
  const rawValue = params.get('query');
  return rawValue?.trim() ?? '';
}

export function getDashboardFilterConfig<TMode extends DashboardMode>(mode: TMode) {
  return filterConfigs[mode];
}

export function parseDashboardFilters<TMode extends DashboardMode>(
  mode: TMode,
  search: string,
): DashboardFiltersByMode[TMode] {
  const params = new URLSearchParams(search);
  const config = getDashboardFilterConfig(mode);

  if (mode === 'posts') {
    return {
      ...config.defaults,
      query: parseQueryValue(params),
      date_from: parseNullableDate(params, 'date_from', config.defaults.date_from) ?? '',
      date_to: parseNullableDate(params, 'date_to', config.defaults.date_to) ?? '',
      limit: parseNumber(params, 'limit', config.defaults.limit) ?? config.defaults.limit,
      channel_ids: parseNumberList(params, 'channel_ids'),
      categories: parseStringList(params, 'categories'),
      min_comments: parseNumber(params, 'min_comments', config.defaults.min_comments),
      report_status: parseStringList(params, 'report_status'),
      sort_by: params.get('sort_by') ?? config.defaults.sort_by,
      sort_order: (params.get('sort_order') as SortOrder | null) ?? config.defaults.sort_order,
    } as DashboardFiltersByMode[TMode];
  }

  if (mode === 'events') {
    return {
      ...config.defaults,
      query: parseQueryValue(params),
      date_from: parseNullableDate(params, 'date_from', config.defaults.date_from),
      date_to: parseNullableDate(params, 'date_to', config.defaults.date_to),
      limit: parseNumber(params, 'limit', config.defaults.limit) ?? config.defaults.limit,
      status: parseStringList(params, 'status'),
      channel_ids: parseNumberList(params, 'channel_ids'),
      categories: parseStringList(params, 'categories'),
      min_comments: parseNumber(params, 'min_comments', config.defaults.min_comments),
      sort_by: params.get('sort_by') ?? config.defaults.sort_by,
      sort_order: (params.get('sort_order') as SortOrder | null) ?? config.defaults.sort_order,
    } as DashboardFiltersByMode[TMode];
  }

  return {
    ...config.defaults,
    query: parseQueryValue(params),
    date_from: parseNullableDate(params, 'date_from', config.defaults.date_from),
    date_to: parseNullableDate(params, 'date_to', config.defaults.date_to),
    limit: parseNumber(params, 'limit', config.defaults.limit) ?? config.defaults.limit,
    status: parseStringList(params, 'status'),
    min_comments: parseNumber(params, 'min_comments', config.defaults.min_comments),
    sort_by: params.get('sort_by') ?? config.defaults.sort_by,
    sort_order: (params.get('sort_order') as SortOrder | null) ?? config.defaults.sort_order,
  } as DashboardFiltersByMode[TMode];
}

export function serializeDashboardFilters<TMode extends DashboardMode>(
  mode: TMode,
  filters: DashboardFiltersByMode[TMode],
) {
  const defaults = getDashboardFilterConfig(mode).defaults;
  const query: Record<string, string | number | Array<string | number> | null | undefined> = {};

  Object.entries(filters).forEach(([key, value]) => {
    const defaultValue = defaults[key as keyof typeof defaults];

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return;
      }

      query[key] = value.join(',');
      return;
    }

    if (value === defaultValue) {
      return;
    }

    if (value === '' || value === null || value === undefined) {
      return;
    }

    query[key] = value;
  });

  return serializeQueryParams(query);
}

export function getDashboardModePath(mode: DashboardMode) {
  return `/dashboard/${mode}`;
}

export function getModeSwitchSearch(currentMode: DashboardMode, nextMode: DashboardMode, currentSearch: string) {
  const currentFilters = parseDashboardFilters(currentMode, currentSearch);
  const nextDefaults = getDashboardFilterConfig(nextMode).defaults;
  const preservedKeys = new Set(getDashboardFilterConfig(nextMode).modeSwitchPreservedKeys);
  const nextFilters = { ...nextDefaults } as DashboardFiltersByMode[typeof nextMode];

  Object.entries(currentFilters).forEach(([key, value]) => {
    if (!preservedKeys.has(key as DashboardFilterKey)) {
      return;
    }

    if (!(key in nextFilters)) {
      return;
    }

    (nextFilters as Record<string, unknown>)[key] = value;
  });

  const query = serializeDashboardFilters(nextMode, nextFilters);
  return query ? `?${query}` : '';
}
