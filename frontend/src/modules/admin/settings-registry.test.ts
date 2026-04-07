import { describe, expect, it } from 'vitest';

import {
  createFallbackSettingsFieldMetadata,
  getSettingsCategoryMetadata,
  getSettingsFieldMetadata,
  getSettingsFieldMetadataOrFallback,
  listSettingsFieldMetadata,
  settingsCategoryOrder,
  settingsRegistryStats,
} from '@modules/admin/settings-registry';

describe('settings registry', () => {
  it('covers every current settings category and all documented fields', () => {
    expect(settingsCategoryOrder).toEqual([
      'ingest',
      'reports',
      'retention',
      'jobs',
      'api',
      'scheduler',
      'comments',
      'monitor',
      'features',
    ]);

    expect(settingsRegistryStats.categoryCount).toBe(9);
    expect(settingsRegistryStats.fieldCount).toBe(63);

    expect(listSettingsFieldMetadata('ingest')).toHaveLength(9);
    expect(listSettingsFieldMetadata('reports')).toHaveLength(5);
    expect(listSettingsFieldMetadata('retention')).toHaveLength(2);
    expect(listSettingsFieldMetadata('jobs')).toHaveLength(9);
    expect(listSettingsFieldMetadata('api')).toHaveLength(1);
    expect(listSettingsFieldMetadata('scheduler')).toHaveLength(3);
    expect(listSettingsFieldMetadata('comments')).toHaveLength(7);
    expect(listSettingsFieldMetadata('monitor')).toHaveLength(25);
    expect(listSettingsFieldMetadata('features')).toHaveLength(2);
  });

  it('returns russian labels and control hints for documented fields', () => {
    const monitorCategory = getSettingsCategoryMetadata('monitor');
    const rolloutField = getSettingsFieldMetadata('features', 'keyword_graph_rollout_percent');
    const schedulerField = getSettingsFieldMetadata('scheduler', 'enabled');

    expect(monitorCategory.label).toBe('Мониторинг');
    expect(monitorCategory.badge).toBe('Технический раздел');

    expect(rolloutField).toMatchObject({
      label: 'Rollout графа ключевых слов, %',
      controlType: 'number',
      unit: 'percent',
      groupHint: 'feature-flags',
      value: {
        kind: 'integer',
        min: 0,
        max: 100,
        allowedValuesLabel: 'int, 0..100',
      },
    });

    expect(schedulerField).toMatchObject({
      label: 'Включить планировщик retention',
      controlType: 'boolean',
      value: {
        kind: 'boolean',
        allowedValuesLabel: 'bool, true/false',
      },
    });
  });

  it('keeps a safe fallback path for unknown backend fields', () => {
    const fallback = createFallbackSettingsFieldMetadata('jobs', 'unexpected_backend_flag', 99);
    const resolved = getSettingsFieldMetadataOrFallback('jobs', 'unexpected_backend_flag', 99);

    expect(fallback).toMatchObject({
      categoryKey: 'jobs',
      key: 'unexpected_backend_flag',
      label: 'unexpected_backend_flag',
      controlType: 'json',
      order: 99,
      value: {
        kind: 'unknown',
        allowedValuesLabel: 'См. backend-контракт',
      },
    });

    expect(resolved).toEqual(fallback);
  });
});
