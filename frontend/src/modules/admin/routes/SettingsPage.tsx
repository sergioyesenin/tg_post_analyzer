import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { SettingsCategoryDetails } from '@modules/admin/components/SettingsCategoryDetails';
import { SettingsCategoryEditor } from '@modules/admin/components/SettingsCategoryEditor';
import { SettingsCategoryNav } from '@modules/admin/components/SettingsCategoryNav';
import { useSettingsMutations, useSettingsQueries } from '@modules/admin/hooks';
import { buildSettingsCategoryViewModels } from '@modules/admin/mappers';
import { settingsCategoryOrder, type SettingsCategoryKey } from '@modules/admin/settings-catalog';
import {
  mapSettingsMutationError,
  parseSettingsPayload,
  updateSettingSchema,
  validateSettingsPayload,
  type SettingsMutationErrorState,
  type UpdateSettingFormValues,
} from '@modules/admin/validation';
import { ApiError } from '@shared/api/client';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function SettingsPage() {
  const { t } = useTranslation();
  const { primaryRole } = useSession();
  const isAdmin = primaryRole === 'admin';
  const { effectiveQuery, settingsQuery } = useSettingsQueries(isAdmin);
  const mutations = useSettingsMutations();
  const settings = settingsQuery.data ?? [];
  const effectiveSettings = effectiveQuery.data ?? {};
  const categories = useMemo(() => buildSettingsCategoryViewModels(settings, effectiveSettings), [effectiveSettings, settings]);
  const [selectedCategoryKey, setSelectedCategoryKey] = useState<SettingsCategoryKey>(settingsCategoryOrder[0]);
  const [mutationErrors, setMutationErrors] = useState<SettingsMutationErrorState>({
    fieldErrors: {},
    sectionError: null,
    serverError: null,
  });
  const selectedCategory = categories.find((category) => category.key === selectedCategoryKey) ?? categories[0] ?? null;

  const form = useForm<UpdateSettingFormValues>({
    resolver: zodResolver(updateSettingSchema),
    defaultValues: {
      description: '',
      value_json_text: '{}',
    },
  });

  useEffect(() => {
    if (!selectedCategory) {
      return;
    }

    form.reset({
      description: selectedCategory.editableSetting?.description ?? '',
      value_json_text: selectedCategory.editableSetting ? JSON.stringify(selectedCategory.editableSetting.value_json, null, 2) : '{}',
    });
    setMutationErrors({
      fieldErrors: {},
      sectionError: null,
      serverError: null,
    });
  }, [form, selectedCategory]);

  const currentJsonText = form.watch('value_json_text');
  const parsedPayload = useMemo(() => parseSettingsPayload(currentJsonText), [currentJsonText]);
  const clientFieldErrors = useMemo(() => {
    if (!selectedCategory || !parsedPayload) {
      return {};
    }

    return validateSettingsPayload(selectedCategory.key, parsedPayload);
  }, [parsedPayload, selectedCategory]);
  const fieldErrors = useMemo(
    () => ({ ...mutationErrors.fieldErrors, ...clientFieldErrors }),
    [clientFieldErrors, mutationErrors.fieldErrors],
  );

  useEffect(() => {
    setMutationErrors((current) =>
      current.sectionError || current.serverError || Object.keys(current.fieldErrors).length > 0
        ? { fieldErrors: {}, sectionError: null, serverError: null }
        : current,
    );
  }, [currentJsonText, selectedCategoryKey]);

  if (effectiveQuery.isLoading || (isAdmin && settingsQuery.isLoading)) {
    return <LoadingState title={t('admin.settings.loadingTitle')} description={t('admin.settings.loadingDescription')} />;
  }

  if (effectiveQuery.isError || (isAdmin && settingsQuery.isError)) {
    const error = effectiveQuery.error ?? settingsQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('admin.settings.forbiddenTitle')} description={t('admin.settings.forbiddenDescription')} />;
    }

    return <ErrorState title={t('admin.settings.errorTitle')} description={t('admin.settings.errorDescription')} />;
  }

  if (!selectedCategory) {
    return <ErrorState title={t('admin.settings.errorTitle')} description={t('admin.settings.emptyDescription')} />;
  }

  return (
    <div className="dashboard-page admin-console-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.admin')}</span>
          <h2>{t('navigation.settings')}</h2>
          <p>{isAdmin ? t('admin.settings.heroDescriptionAdmin') : t('admin.settings.heroDescriptionAnalyst')}</p>
        </div>
      </section>

      {!isAdmin ? (
        <ReadOnlyNotice
          title={t('admin.settings.readOnlyTitle')}
          description={t('admin.settings.readOnlyDescription')}
          ariaLabel={t('admin.settings.readOnlyAria')}
        />
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace settings-page__content">
        <div className="dashboard-page__primary settings-page__primary">
          <SettingsCategoryNav categories={categories} selectedCategoryKey={selectedCategoryKey} onSelect={setSelectedCategoryKey} />
          <SettingsCategoryDetails category={selectedCategory} />
        </div>

        <div className="dashboard-page__secondary settings-page__secondary">
          <SettingsCategoryEditor
            category={selectedCategory}
            isAdmin={isAdmin}
            form={form}
            isSubmitting={mutations.update.isPending}
            fieldErrors={fieldErrors}
            sectionError={mutationErrors.sectionError}
            serverError={mutationErrors.serverError}
            onSubmit={async () => {
              if (!selectedCategory.editableSetting) {
                return;
              }

              const isBaseValid = await form.trigger();
              const payload = parseSettingsPayload(form.getValues('value_json_text'));
              const nextClientErrors = payload ? validateSettingsPayload(selectedCategory.key, payload) : {};

              if (!isBaseValid || !payload || Object.keys(nextClientErrors).length > 0) {
                setMutationErrors({
                  fieldErrors: nextClientErrors,
                  sectionError: Object.keys(nextClientErrors).length > 0 ? t('admin.settings.validationSectionDescription') : null,
                  serverError: null,
                });
                return;
              }

              if (!window.confirm(t('admin.settings.confirmUpdate', { key: selectedCategory.label }))) {
                return;
              }

              const values = form.getValues();
              setMutationErrors({
                fieldErrors: {},
                sectionError: null,
                serverError: null,
              });

              try {
                await mutations.update.mutateAsync({
                  key: selectedCategory.key,
                  payload: {
                    description: values.description || null,
                    value_json: payload,
                  },
                });
              } catch (error) {
                setMutationErrors(mapSettingsMutationError(error, selectedCategory.key, payload));
              }
            }}
          />
        </div>
      </section>
    </div>
  );
}
