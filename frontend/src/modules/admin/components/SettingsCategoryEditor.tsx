import { useMemo } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import type { SettingsCategoryViewModel } from '@modules/admin/mappers';
import { SettingsFieldRenderer } from '@modules/admin/components/SettingsFieldRenderer';
import type { UpdateSettingFormValues } from '@modules/admin/validation';
import { formatUtcDateTime } from '@shared/utils/formatters';

type SettingsCategoryEditorProps = {
  category: SettingsCategoryViewModel;
  isAdmin: boolean;
  form: UseFormReturn<UpdateSettingFormValues>;
  isSubmitting: boolean;
  fieldErrors: Record<string, string>;
  sectionError: string | null;
  serverError: string | null;
  onSubmit: () => void;
};

function parseEditablePayload(value: string, fallback: Record<string, unknown>): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return fallback;
  }

  return fallback;
}

export function SettingsCategoryEditor({
  category,
  isAdmin,
  form,
  isSubmitting,
  fieldErrors,
  sectionError,
  serverError,
  onSubmit,
}: SettingsCategoryEditorProps) {
  const { t } = useTranslation();
  const prettyEffective = JSON.stringify(category.effectiveValue, null, 2);
  const currentJsonText = form.watch('value_json_text');
  const editablePayload = useMemo(
    () => parseEditablePayload(currentJsonText, category.editableSetting?.value_json ?? {}),
    [category.editableSetting?.value_json, currentJsonText],
  );
  const resolvedValues = useMemo(() => ({ ...category.effectiveValue, ...editablePayload }), [category.effectiveValue, editablePayload]);
  const isEditable = isAdmin && Boolean(category.editableSetting);

  const updateFieldValue = (key: string, value: unknown) => {
    const nextPayload = { ...editablePayload };

    if (value === undefined) {
      delete nextPayload[key];
    } else {
      nextPayload[key] = value;
    }

    form.setValue('value_json_text', JSON.stringify(nextPayload, null, 2), {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  return (
    <div className="settings-category-editor">
      <section className="detail-block settings-editor-card">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{isAdmin ? t('states.update') : t('states.readOnly')}</span>
            <strong>{isAdmin ? t('admin.settings.editAreaTitle') : t('admin.settings.readOnlyPanelTitle')}</strong>
          </div>
        </div>

        <form className="dashboard-filter-grid admin-console-form" onSubmit={form.handleSubmit(onSubmit)}>
          {isAdmin ? (
            <label className="admin-console-form__field">
              <span>{t('fields.description')}</span>
              <input {...form.register('description')} disabled={!isEditable} />
            </label>
          ) : null}

          {!isEditable ? (
            <div className="workspace-selection-context">
              <strong>{isAdmin ? t('admin.settings.noEditablePayloadTitle') : t('admin.settings.readOnlyPanelTitle')}</strong>
              <p>{isAdmin ? t('admin.settings.noEditablePayloadDescription') : t('admin.settings.readOnlyPanelDescription')}</p>
            </div>
          ) : null}

          {sectionError ? (
            <div className="workspace-selection-context">
              <strong>{t('admin.settings.validationSectionTitle')}</strong>
              <p>{sectionError}</p>
            </div>
          ) : null}

          {serverError ? (
            <div className="workspace-selection-context">
              <strong>{t('states.error')}</strong>
              <p>{serverError}</p>
            </div>
          ) : null}

          <SettingsFieldRenderer
            parameters={category.parameters}
            values={resolvedValues}
            errors={fieldErrors}
            readOnly={!isEditable}
            onChange={updateFieldValue}
          />

          <input type="hidden" {...form.register('value_json_text')} />

          <details className="settings-editor-card__technical">
            <summary>{t('admin.settings.jsonEditorLabel')}</summary>
            <label className="admin-console-form__field">
              <span>{t('admin.settings.jsonEditorLabel')}</span>
              <textarea
                rows={10}
                disabled={!isEditable}
                aria-invalid={Boolean(form.formState.errors.value_json_text)}
                className={form.formState.errors.value_json_text ? 'dashboard-filter-input--invalid' : ''}
                {...form.register('value_json_text')}
              />
              <small>{t('admin.settings.jsonEditorHint')}</small>
              {form.formState.errors.value_json_text ? (
                <small className="dashboard-filter-field__error">{form.formState.errors.value_json_text.message}</small>
              ) : null}
            </label>
          </details>

          {category.editableSetting ? (
            <div className="settings-editor-card__meta">
              <span>{t('admin.settings.updatedAtLabel')}: {formatUtcDateTime(category.editableSetting.updated_at)}</span>
              <span>
                {t('admin.settings.updatedByLabel')}: {category.editableSetting.updated_by_user_id === null ? t('admin.common.system') : category.editableSetting.updated_by_user_id}
              </span>
            </div>
          ) : null}

          {isEditable ? (
            <div className="dashboard-filter-bar__actions admin-console-actions settings-editor-card__actions">
              <button
                type="submit"
                className="admin-console-button admin-console-button--primary"
                disabled={isSubmitting || Boolean(form.formState.errors.value_json_text) || Object.keys(fieldErrors).length > 0}
              >
                {t('actions.saveSetting')}
              </button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="detail-block settings-editor-card">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{t('states.effective')}</span>
            <strong>{t('admin.settings.effectivePanelTitle')}</strong>
          </div>
        </div>
        <pre className="route-placeholder__code-block settings-editor-card__code">{prettyEffective}</pre>
      </section>
    </div>
  );
}
