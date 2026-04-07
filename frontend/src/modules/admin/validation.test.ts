import { describe, expect, it } from 'vitest';

import { ApiError } from '@shared/api/client';
import { mapSettingsMutationError, validateSettingsPayload } from '@modules/admin/validation';

describe('settings validation', () => {
  it('validates known field bounds and preserves valid 0, false, and 0.0 values', () => {
    expect(
      validateSettingsPayload('comments', {
        sleep_base_sec: 0,
        sleep_jitter_sec: 0,
        reconciliation_enabled: false,
      }),
    ).toEqual({});

    expect(
      validateSettingsPayload('jobs', {
        ai_poll_seconds: 4000,
      }),
    ).toEqual({
      ai_poll_seconds: 'Для поля «Интервал опроса AI-очереди, сек» допустим диапазон от 5 до 3600',
    });

    expect(
      validateSettingsPayload('scheduler', {
        enabled: 'yes',
      }),
    ).toEqual({
      enabled: 'Для поля «Включить планировщик retention» нужно указать значение да или нет',
    });
  });

  it('returns a dedicated server error for non-validation failures', () => {
    expect(mapSettingsMutationError(new ApiError('Failed', 500), 'jobs', {})).toEqual({
      fieldErrors: {},
      sectionError: null,
      serverError: 'Не удалось сохранить настройки. Повторите позже.',
    });
  });

  it('maps backend 422 payload to field and section errors', () => {
    const error = new ApiError('Validation failed', 422, {
      detail: [
        {
          loc: ['body', 'value_json', 'ai_poll_seconds'],
          msg: 'Input should be less than or equal to 3600',
        },
      ],
    });

    expect(
      mapSettingsMutationError(error, 'jobs', {
        ai_poll_seconds: 4000,
      }),
    ).toEqual({
      fieldErrors: {
        ai_poll_seconds: 'Для поля «Интервал опроса AI-очереди, сек» допустим диапазон от 5 до 3600',
      },
      sectionError: 'Сохранение отклонено из-за невалидных значений. Проверьте поля и повторите.',
      serverError: null,
    });
  });
});

