import type { TFunction } from 'i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import { getDashboardFilterConfig, type DashboardFiltersByMode } from '@shared/dashboard/filters';

export type DashboardFilterFeedback = {
  tone: 'info' | 'warning' | 'danger';
  title: string;
  description: string;
};

export type DashboardEmptyStateCopy = {
  filterBar: DashboardFilterFeedback;
  stateCard: {
    title: string;
    description: string;
  };
};

const narrowingKeysByMode: Record<DashboardMode, string[]> = {
  posts: ['date_from', 'date_to', 'channel_ids', 'categories', 'min_comments', 'report_status'],
  events: ['date_from', 'date_to', 'status', 'channel_ids', 'categories', 'min_comments'],
  processes: ['date_from', 'date_to', 'status', 'min_comments'],
};

function valuesEqual(left: unknown, right: unknown) {
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => value === right[index]);
  }

  return left === right;
}

export function hasNarrowingDashboardFilters<TMode extends DashboardMode>(mode: TMode, filters: DashboardFiltersByMode[TMode]) {
  const defaults = getDashboardFilterConfig(mode).defaults as Record<string, unknown>;
  const typedFilters = filters as Record<string, unknown>;

  return narrowingKeysByMode[mode].some((key) => !valuesEqual(typedFilters[key], defaults[key]));
}

export function getDashboardEmptyFeedback<TMode extends DashboardMode>(
  mode: TMode,
  filters: DashboardFiltersByMode[TMode],
  t: TFunction,
): DashboardEmptyStateCopy {
  if (hasNarrowingDashboardFilters(mode, filters)) {
    return {
      filterBar: {
        tone: 'warning',
        title: t('dashboard.filters.feedback.emptyNarrow.title'),
        description: t('dashboard.filters.feedback.emptyNarrow.description'),
      },
      stateCard: {
        title: t('dashboard.filters.state.emptyNarrow.title'),
        description: t('dashboard.filters.state.emptyNarrow.description'),
      },
    };
  }

  return {
    filterBar: {
      tone: 'info',
      title: t('dashboard.filters.feedback.emptySnapshot.title'),
      description: t('dashboard.filters.feedback.emptySnapshot.description'),
    },
    stateCard: {
      title: t('dashboard.filters.state.emptySnapshot.title'),
      description: t('dashboard.filters.state.emptySnapshot.description'),
    },
  };
}

export function getDashboardErrorFilterFeedback(t: TFunction) {
  return {
    tone: 'danger',
    title: t('dashboard.filters.feedback.requestError.title'),
    description: t('dashboard.filters.feedback.requestError.description'),
  } satisfies DashboardFilterFeedback;
}
