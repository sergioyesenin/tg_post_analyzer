import type { TFunction } from 'i18next';

import type { UserRole } from '@shared/auth/roles';
import { ApiError } from '@shared/api/client';
import type { DashboardFilterFeedback } from '@shared/dashboard/filter-feedback';

export function isDashboardSearchAllowedForRole(role: UserRole | null) {
  return role === 'admin' || role === 'analyst';
}

export function getDashboardSearchDisabledReason(role: UserRole | null, t: TFunction) {
  if (isDashboardSearchAllowedForRole(role)) {
    return null;
  }

  return t('dashboard.search.roleUnavailable', {
    defaultValue: 'Поиск недоступен для этой роли',
  });
}

export function getDashboardSearchAvailabilityFeedback(error: unknown, t: TFunction): DashboardFilterFeedback | null {
  if (!(error instanceof ApiError)) {
    return null;
  }

  if (error.status === 404) {
    return {
      tone: 'warning',
      title: t('dashboard.search.unavailableTitle', {
        defaultValue: 'Поиск пока недоступен в этом рабочем пространстве',
      }),
      description: t('dashboard.search.unavailableDescription', {
        defaultValue: 'Для этой учетной записи поиск по ключевым словам пока не включен.',
      }),
    };
  }

  if (error.status === 403) {
    return {
      tone: 'warning',
      title: t('dashboard.search.forbiddenTitle', {
        defaultValue: 'Поиск недоступен для этой роли',
      }),
      description: t('dashboard.search.forbiddenDescription', {
        defaultValue: 'У вашей роли нет доступа к поиску по ключевым словам.',
      }),
    };
  }

  return null;
}
