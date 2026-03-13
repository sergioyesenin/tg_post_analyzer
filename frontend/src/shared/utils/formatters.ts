export function formatUtcDateTime(value: string | null | undefined, fallback = 'n/a') {
  if (!value) {
    return fallback;
  }

  return new Intl.DateTimeFormat('en-US', {
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
  const fallback = options?.fallback ?? 'n/a';
  const locale = options?.locale ?? 'en-US';

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
  const fallback = options?.fallback ?? 'n/a';
  const digits = options?.digits ?? 2;

  if (value === null || value === undefined) {
    return fallback;
  }

  return value.toFixed(digits);
}

export function formatConfidencePercent(value: number | null | undefined, fallback = 'n/a') {
  if (value === null || value === undefined) {
    return fallback;
  }

  return `${Math.round(value * 100)}%`;
}
