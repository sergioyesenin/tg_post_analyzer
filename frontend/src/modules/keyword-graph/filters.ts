import type { KeywordSearchFilters } from '@modules/keyword-graph/contracts';
import { parseQueryParams, serializeQueryParams } from '@shared/utils/queryParams';

function parseNumber(value: string | string[] | undefined, fallback: number) {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = raw ? Number(raw) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseNumberArray(value: string | string[] | undefined) {
  const values = Array.isArray(value) ? value : value ? [value] : [];

  return values
    .flatMap((item) => item.split(','))
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

export function getDefaultKeywordSearchFilters(): KeywordSearchFilters {
  return {
    query: '',
    limit: 50,
    date_from: '',
    date_to: '',
    channel_ids: [],
  };
}

export function parseKeywordSearchFilters(search: string): KeywordSearchFilters {
  const params = parseQueryParams(search);
  const defaults = getDefaultKeywordSearchFilters();

  return {
    query: String(Array.isArray(params.query) ? params.query[0] ?? '' : params.query ?? ''),
    limit: parseNumber(params.limit, defaults.limit),
    date_from: String(Array.isArray(params.date_from) ? params.date_from[0] ?? '' : params.date_from ?? ''),
    date_to: String(Array.isArray(params.date_to) ? params.date_to[0] ?? '' : params.date_to ?? ''),
    channel_ids: parseNumberArray(params.channel_ids),
  };
}

export function serializeKeywordSearchFilters(filters: KeywordSearchFilters) {
  return serializeQueryParams({
    query: filters.query,
    limit: filters.limit,
    date_from: filters.date_from,
    date_to: filters.date_to,
    channel_ids: filters.channel_ids,
  });
}
