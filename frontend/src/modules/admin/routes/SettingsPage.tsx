import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

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
    values: {
      description: selectedSetting?.description ?? '',
      value_json_text: selectedSetting ? JSON.stringify(selectedSetting.value_json, null, 2) : '{}',
    },
  });

  if (effectiveQuery.isLoading || (isAdmin && settingsQuery.isLoading)) {
    return <LoadingState title="Loading settings" description="Fetching effective settings and editable settings keys." />;
  }

  if (effectiveQuery.isError || (isAdmin && settingsQuery.isError)) {
    const error = effectiveQuery.error ?? settingsQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title="Settings module is restricted" description="Your role cannot access this settings view." />;
    }

    return <ErrorState title="Settings failed to load" description="The settings request failed." />;
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">admin</span>
          <h2>Settings</h2>
          <p>{isAdmin ? 'Admin can review effective values and update supported setting groups.' : 'Analyst access is read-only and limited to effective settings.'}</p>
        </div>
      </section>

      {!isAdmin ? (
        <ReadOnlyNotice
          title="Analyst access is limited to effective settings"
          description="Editable settings keys and update actions remain admin-only."
          ariaLabel="Read only settings notice"
        />
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {isAdmin ? (
            settings.length === 0 ? (
              <EmptyState title="No editable settings available" description="The settings list endpoint returned an empty list." />
            ) : (
              <AdminDataGrid
                title="Settings grid"
                description="Editable settings registry for admin users."
                columns={settingsColumns}
                rows={mapSettingsToRows(settings).map((row) => ({
                  ...row,
                  isSelected: row.id === selectedKey,
                  cells: {
                    ...row.cells,
                    key: (
                      <button type="button" className="dashboard-button dashboard-button--ghost" onClick={() => setSelectedKey(String(row.id))}>
                        {row.id === selectedKey ? `${row.id} (selected)` : row.id}
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
                  <span className="state-card__eyebrow">effective settings</span>
                  <strong>Effective settings payload</strong>
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
                <span className="state-card__eyebrow">effective</span>
                <strong>Effective settings</strong>
              </div>
            </div>
            <pre className="route-placeholder__code-block">{prettyEffective}</pre>
          </section>

          {isAdmin ? (
            <section className="detail-block">
              <div className="detail-block__header">
                <div>
                  <span className="state-card__eyebrow">update</span>
                  <strong>{selectedSetting?.key ?? 'Selected setting'}</strong>
                </div>
              </div>

              {selectedSetting ? (
                <form
                  className="dashboard-filter-grid"
                  onSubmit={form.handleSubmit(async (values) => {
                    if (!window.confirm(`Update setting ${selectedSetting.key}?`)) {
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
                    <span>Description</span>
                    <input {...form.register('description')} />
                  </label>
                  <label>
                    <span>Value JSON</span>
                    <textarea rows={12} {...form.register('value_json_text')} />
                    {form.formState.errors.value_json_text ? <small>{form.formState.errors.value_json_text.message}</small> : null}
                  </label>
                  <div className="dashboard-filter-bar__actions">
                    <button type="submit" className="dashboard-button" disabled={mutations.update.isPending}>
                      Save setting
                    </button>
                  </div>
                </form>
              ) : (
                <p className="dashboard-panel-copy">Select a settings row to edit its JSON payload.</p>
              )}
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}
