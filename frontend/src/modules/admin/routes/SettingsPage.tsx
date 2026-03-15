import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { useSettingsMutations, useSettingsQueries } from '@modules/admin/hooks';
import { mapSettingsToRows, settingsColumns } from '@modules/admin/mappers';
import { updateSettingSchema, type UpdateSettingFormValues } from '@modules/admin/validation';
import { ApiError } from '@shared/api/client';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
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
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const selectedSetting = settings.find((item) => item.key === selectedKey) ?? null;

  useEffect(() => {
    if (!isAdmin || settings.length === 0) {
      setSelectedKey(null);
      return;
    }

    setSelectedKey((current) => (current && settings.some((item) => item.key === current) ? current : settings[0]!.key));
  }, [isAdmin, settings]);

  const prettyEffective = useMemo(
    () => JSON.stringify(effectiveQuery.data ?? {}, null, 2),
    [effectiveQuery.data],
  );

  const form = useForm<UpdateSettingFormValues>({
    resolver: zodResolver(updateSettingSchema),
    defaultValues: {
      description: '',
      value_json_text: '{}',
    },
  });

  useEffect(() => {
    form.reset({
      description: selectedSetting?.description ?? '',
      value_json_text: selectedSetting ? JSON.stringify(selectedSetting.value_json, null, 2) : '{}',
    });
  }, [form, selectedSetting]);

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

  return (
    <div className="dashboard-page">
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

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {isAdmin ? (
            settings.length === 0 ? (
              <EmptyState title={t('admin.settings.emptyTitle')} description={t('admin.settings.emptyDescription')} />
            ) : (
              <AdminDataGrid
                title={t('admin.settings.gridTitle')}
                description={t('admin.settings.gridDescription')}
                columns={settingsColumns}
                rows={mapSettingsToRows(settings).map((row) => ({
                  ...row,
                  isSelected: row.id === selectedKey,
                  cells: {
                    ...row.cells,
                    key: (
                      <button type="button" className="dashboard-button dashboard-button--ghost" onClick={() => setSelectedKey(String(row.id))}>
                        {row.id === selectedKey ? t('admin.settings.selectedKey', { key: row.id }) : row.id}
                      </button>
                    ),
                  },
                }))}
              />
            )
          ) : (
            <section className="detail-block">
              <div className="detail-block__header">
                <div>
                  <span className="state-card__eyebrow">{t('states.effectiveSettings')}</span>
                  <strong>{t('admin.settings.effectivePayloadTitle')}</strong>
                </div>
              </div>
              <pre className="route-placeholder__code-block">{prettyEffective}</pre>
            </section>
          )}
        </div>

        <div className="dashboard-page__secondary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.effective')}</span>
                <strong>{t('admin.settings.effectiveTitle')}</strong>
              </div>
            </div>
            <pre className="route-placeholder__code-block">{prettyEffective}</pre>
          </section>

          {isAdmin ? (
            <section className="detail-block">
              <div className="detail-block__header">
                <div>
                  <span className="state-card__eyebrow">{t('states.update')}</span>
                  <strong>{selectedSetting?.key ?? t('admin.settings.selectedSetting')}</strong>
                </div>
              </div>

              {selectedSetting ? (
                <form
                  className="dashboard-filter-grid"
                  onSubmit={form.handleSubmit(async (values) => {
                    if (!window.confirm(t('admin.settings.confirmUpdate', { key: selectedSetting.key }))) {
                      return;
                    }

                    await mutations.update.mutateAsync({
                      key: selectedSetting.key,
                      payload: {
                        description: values.description || null,
                        value_json: JSON.parse(values.value_json_text) as Record<string, unknown>,
                      },
                    });
                  })}
                >
                  <label>
                    <span>{t('fields.description')}</span>
                    <input {...form.register('description')} />
                  </label>
                  <label>
                    <span>{t('fields.valueJson')}</span>
                    <textarea rows={12} {...form.register('value_json_text')} />
                    {form.formState.errors.value_json_text ? <small>{form.formState.errors.value_json_text.message}</small> : null}
                  </label>
                  <div className="dashboard-filter-bar__actions">
                    <button type="submit" className="dashboard-button" disabled={mutations.update.isPending}>
                      {t('actions.saveSetting')}
                    </button>
                  </div>
                </form>
              ) : (
                <p className="dashboard-panel-copy">{t('admin.settings.selectionHint')}</p>
              )}
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}
