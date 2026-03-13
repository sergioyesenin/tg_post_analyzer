import { parseQueryParams, serializeQueryParams } from '@shared/utils/queryParams';
import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';

function parseStringArray(value: string | string[] | undefined) {
  if (!value) {
    return [];
  }

  const values = Array.isArray(value) ? value : [value];
  return values
    .flatMap((item) => item.split(','))
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseNumberArray(value: string | string[] | undefined) {
  return parseStringArray(value).map((item) => Number(item)).filter((item) => Number.isFinite(item));
}

function parseNumber(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) {
    return null;
  }

  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseDate(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw ?? '';
}

export function getDefaultReportsFilters<TType extends ReportType>(type: TType): ReportsFiltersByType[TType] {
  if (type === 'posts') {
    return {
      channel_ids: [],
      categories: [],
      date_from: '',
      date_to: '',
      min_comments: null,
      limit: 100,
      offset: 0,
    } as unknown as ReportsFiltersByType[TType];
  }

  if (type === 'events') {
    return {
      event_id: null,
      date_from: '',
      date_to: '',
      limit: 100,
      offset: 0,
    } as unknown as ReportsFiltersByType[TType];
  }

  return {
    process_id: null,
    date_from: '',
    date_to: '',
    limit: 100,
    offset: 0,
  } as unknown as ReportsFiltersByType[TType];
}

export function parseReportsFilters<TType extends ReportType>(type: TType, search: string): ReportsFiltersByType[TType] {
  const params = parseQueryParams(search);
  const defaults = getDefaultReportsFilters(type);

  if (type === 'posts') {
    return {
      ...defaults,
      channel_ids: parseNumberArray(params.channel_ids),
      categories: parseStringArray(params.categories),
      date_from: parseDate(params.date_from),
      date_to: parseDate(params.date_to),
      min_comments: parseNumber(params.min_comments),
      limit: parseNumber(params.limit) ?? defaults.limit,
      offset: parseNumber(params.offset) ?? defaults.offset,
    } as ReportsFiltersByType[TType];
  }

  if (type === 'events') {
    return {
      ...defaults,
      event_id: parseNumber(params.event_id),
      date_from: parseDate(params.date_from),
      date_to: parseDate(params.date_to),
      limit: parseNumber(params.limit) ?? defaults.limit,
      offset: parseNumber(params.offset) ?? defaults.offset,
    } as ReportsFiltersByType[TType];
  }

  return {
    ...defaults,
    process_id: parseNumber(params.process_id),
    date_from: parseDate(params.date_from),
    date_to: parseDate(params.date_to),
    limit: parseNumber(params.limit) ?? defaults.limit,
    offset: parseNumber(params.offset) ?? defaults.offset,
  } as ReportsFiltersByType[TType];
}

export function serializeReportsFilters<TType extends ReportType>(type: TType, filters: ReportsFiltersByType[TType]) {
  if (type === 'posts') {
    const typed = filters as ReportsFiltersByType['posts'];
    return serializeQueryParams({
      channel_ids: typed.channel_ids,
      categories: typed.categories,
      date_from: typed.date_from,
      date_to: typed.date_to,
      min_comments: typed.min_comments,
      limit: typed.limit,
      offset: typed.offset,
    });
  }

  if (type === 'events') {
    const typed = filters as ReportsFiltersByType['events'];
    return serializeQueryParams({
      event_id: typed.event_id,
      date_from: typed.date_from,
      date_to: typed.date_to,
      limit: typed.limit,
      offset: typed.offset,
    });
  }

  const typed = filters as ReportsFiltersByType['processes'];
  return serializeQueryParams({
    process_id: typed.process_id,
    date_from: typed.date_from,
    date_to: typed.date_to,
    limit: typed.limit,
    offset: typed.offset,
  });
}

export function getReportsPath(type: ReportType) {
  return `/reports/${type}`;
}
