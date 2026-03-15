import { i18n } from '@shared/i18n/i18n';

export function formatUtcDateTime(value: string | null | undefined, fallback = 'n/a') {
  if (!value) {
    return fallback === 'n/a' ? i18n.t('common.na') : fallback;
  }

  return new Intl.DateTimeFormat(i18n.resolvedLanguage === 'ru' ? 'ru-RU' : 'en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

export function formatNullableNumber(
  value: number | null | undefined,
  options?: {
    fallback?: string;
    locale?: string;
  },
) {
  const fallback = options?.fallback ?? i18n.t('common.na');
  const locale = options?.locale ?? (i18n.resolvedLanguage === 'ru' ? 'ru-RU' : 'en-US');

  if (value === null || value === undefined) {
    return fallback;
  }

  return new Intl.NumberFormat(locale).format(value);
}

export function formatNullableRatio(
  value: number | null | undefined,
  options?: {
    fallback?: string;
    digits?: number;
  },
) {
  const fallback = options?.fallback ?? i18n.t('common.na');
  const digits = options?.digits ?? 2;

  if (value === null || value === undefined) {
    return fallback;
  }

  return value.toFixed(digits);
}

export function formatConfidencePercent(value: number | null | undefined, fallback = i18n.t('common.na')) {
  if (value === null || value === undefined) {
    return fallback;
  }

  return `${Math.round(value * 100)}%`;
}
