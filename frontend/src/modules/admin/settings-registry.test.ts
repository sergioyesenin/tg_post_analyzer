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
    expect(settingsRegistryStats.fieldCount).toBe(68);

    expect(listSettingsFieldMetadata('ingest')).toHaveLength(9);
    expect(listSettingsFieldMetadata('reports')).toHaveLength(5);
    expect(listSettingsFieldMetadata('retention')).toHaveLength(2);
    expect(listSettingsFieldMetadata('jobs')).toHaveLength(9);
    expect(listSettingsFieldMetadata('api')).toHaveLength(1);
    expect(listSettingsFieldMetadata('scheduler')).toHaveLength(3);
    expect(listSettingsFieldMetadata('comments')).toHaveLength(10);
    expect(listSettingsFieldMetadata('monitor')).toHaveLength(25);
    expect(listSettingsFieldMetadata('features')).toHaveLength(4);
  });

  it('returns russian labels and control hints for documented fields', () => {
    const monitorCategory = getSettingsCategoryMetadata('monitor');
    const rolloutField = getSettingsFieldMetadata('features', 'keyword_graph_rollout_percent');
    const multiAgentEnabledField = getSettingsFieldMetadata('features', 'multi_agent_mode_enabled');
    const multiAgentRolloutField = getSettingsFieldMetadata('features', 'multi_agent_rollout_percent');
    const schedulerField = getSettingsFieldMetadata('scheduler', 'enabled');
    const longCommentThresholdField = getSettingsFieldMetadata('comments', 'long_comment_threshold');

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

    expect(multiAgentEnabledField).toMatchObject({
      label: 'Включить multi-agent режим',
      controlType: 'boolean',
      groupHint: 'feature-flags',
      value: {
        kind: 'boolean',
        allowedValuesLabel: 'bool, true/false',
      },
    });

    expect(multiAgentRolloutField).toMatchObject({
      label: 'Rollout multi-agent режима, %',
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

    expect(longCommentThresholdField).toMatchObject({
      label: 'Порог длинного комментария, символов',
      controlType: 'number',
      unit: null,
      groupHint: 'comment-reconciliation',
      value: {
        kind: 'integer',
        min: 1,
        max: 10000,
        allowedValuesLabel: 'int, 1..10000',
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
