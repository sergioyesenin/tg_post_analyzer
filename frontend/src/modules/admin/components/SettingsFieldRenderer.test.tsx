import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SettingsFieldRenderer } from '@modules/admin/components/SettingsFieldRenderer';
import type { SettingsParameterViewModel } from '@modules/admin/mappers';

const parameters: SettingsParameterViewModel[] = [
  {
    key: 'enabled',
    label: 'Включить планировщик retention',
    allowedValues: 'bool, true/false',
    purpose: 'Глобальный переключатель APScheduler-процесса.',
    controlType: 'boolean',
    unit: null,
    valueMetadata: { kind: 'boolean', allowedValuesLabel: 'bool, true/false', trueLabel: 'true', falseLabel: 'false' },
    order: 1,
    groupHint: 'scheduler',
    effectiveDisplayValue: 'Да',
    editableDisplayValue: 'Да',
    hasEditableValue: true,
    isDocumented: true,
  },
  {
    key: 'retention_hour',
    label: 'Час запуска retention',
    allowedValues: 'int, 0..23',
    purpose: 'Час ежедневного запуска retention jobs.',
    controlType: 'number',
    unit: 'hours',
    valueMetadata: { kind: 'integer', min: 0, max: 23, allowedValuesLabel: 'int, 0..23' },
    order: 2,
    groupHint: 'scheduler',
    effectiveDisplayValue: '3',
    editableDisplayValue: '3',
    hasEditableValue: true,
    isDocumented: true,
  },
  {
    key: 'ai_scheduler_limit',
    label: 'Лимит постановки AI-отчётов',
    allowedValues: 'int, 1..10000',
    purpose: 'Сколько AI jobs можно поставить за один цикл планировщика.',
    controlType: 'number',
    unit: null,
    valueMetadata: { kind: 'integer', min: 1, max: 10000, allowedValuesLabel: 'int, 1..10000' },
    order: 3,
    groupHint: 'jobs-ai',
    effectiveDisplayValue: '20',
    editableDisplayValue: '20',
    hasEditableValue: true,
    isDocumented: true,
  },
  {
    key: 'collect_comments_flood_rate_warn',
    label: 'Flood rate комментариев: warning',
    allowedValues: 'float, 0.0..1.0',
    purpose: 'Порог warning по доле FloodWait ошибок.',
    controlType: 'number',
    unit: null,
    valueMetadata: { kind: 'float', min: 0, max: 1, allowedValuesLabel: 'float, 0.0..1.0' },
    order: 4,
    groupHint: 'thresholds-flood',
    effectiveDisplayValue: '0.25',
    editableDisplayValue: '0.25',
    hasEditableValue: true,
    isDocumented: true,
  },
  {
    key: 'unexpected_backend_flag',
    label: 'unexpected_backend_flag',
    allowedValues: 'См. backend-контракт',
    purpose: 'Параметр пришёл с backend, но пока не описан в каталоге настроек.',
    controlType: 'json',
    unit: null,
    valueMetadata: { kind: 'unknown', allowedValuesLabel: 'См. backend-контракт' },
    order: 5,
    groupHint: undefined,
    effectiveDisplayValue: '{"mode":"safe"}',
    editableDisplayValue: '{"mode":"safe"}',
    hasEditableValue: true,
    isDocumented: false,
  },
];

describe('SettingsFieldRenderer', () => {
  it('renders typed controls and grouped sections for known metadata', () => {
    render(
      <SettingsFieldRenderer
        parameters={parameters}
        values={{
          enabled: true,
          retention_hour: 3,
          ai_scheduler_limit: 20,
          collect_comments_flood_rate_warn: 0.25,
          unexpected_backend_flag: { mode: 'safe' },
        }}
        readOnly={false}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole('switch', { name: /Включить планировщик retention/i })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: /Час запуска retention/i })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /Лимит постановки AI-отчётов/i })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /Flood rate комментариев: warning/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /unexpected_backend_flag/i })).toBeInTheDocument();
    expect(screen.getByText('Параметры планировщика')).toBeInTheDocument();
  });

  it('shows field-level errors next to matching controls', () => {
    render(
      <SettingsFieldRenderer
        parameters={parameters}
        values={{ ai_scheduler_limit: 10001 }}
        errors={{ ai_scheduler_limit: 'Введите значение от 1 до 10000' }}
        readOnly={false}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText('Введите значение от 1 до 10000')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /Лимит постановки AI-отчётов/i })).toHaveAttribute('aria-invalid', 'true');
  });

  it('supports editing through typed controls and disables them in read-only mode', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    const { rerender } = render(
      <SettingsFieldRenderer parameters={parameters} values={{ enabled: true, retention_hour: 3 }} readOnly={false} onChange={onChange} />,
    );

    await user.click(screen.getByRole('switch', { name: /Включить планировщик retention/i }));
    expect(onChange).toHaveBeenCalledWith('enabled', false);

    fireEvent.change(screen.getByRole('spinbutton', { name: /Лимит постановки AI-отчётов/i }), { target: { value: '42' } });
    expect(onChange).toHaveBeenCalledWith('ai_scheduler_limit', 42);

    rerender(
      <SettingsFieldRenderer parameters={parameters} values={{ enabled: true, retention_hour: 3 }} readOnly={true} onChange={onChange} />,
    );

    expect(screen.getByRole('switch', { name: /Включить планировщик retention/i })).toBeDisabled();
    expect(screen.getByRole('slider', { name: /Час запуска retention/i })).toBeDisabled();
  });
});
