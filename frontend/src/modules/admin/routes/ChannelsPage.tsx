import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { useChannelsQuery, useChannelMutations } from '@modules/admin/hooks';
import { mapChannelsToRows, channelsColumns } from '@modules/admin/mappers';
import { addChannelSchema, type AddChannelFormValues, updateChannelSchema, type UpdateChannelFormValues } from '@modules/admin/validation';
import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { ApiError } from '@shared/api/client';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function ChannelsPage() {
  const { t } = useTranslation();
  const channelsQuery = useChannelsQuery();
  const mutations = useChannelMutations();
  const channels = channelsQuery.data ?? [];
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null);
  const selectedChannel = channels.find((channel) => channel.id === selectedChannelId) ?? null;

  useEffect(() => {
    if (channels.length === 0) {
      setSelectedChannelId(null);
      return;
    }

    setSelectedChannelId((current) => (current && channels.some((channel) => channel.id === current) ? current : channels[0]!.id));
  }, [channels]);

  const addForm = useForm<AddChannelFormValues>({
    resolver: zodResolver(addChannelSchema),
    defaultValues: { username: '' },
  });

  const editForm = useForm<UpdateChannelFormValues>({
    resolver: zodResolver(updateChannelSchema),
    values: {
      title: selectedChannel?.title ?? '',
      category: selectedChannel?.category ?? '',
      is_active: selectedChannel?.is_active ?? true,
    },
  });

  if (channelsQuery.isLoading) {
    return <LoadingState title={t('admin.channels.loadingTitle')} description={t('admin.channels.loadingDescription')} />;
  }

  if (channelsQuery.isError) {
    const error = channelsQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('admin.channels.forbiddenTitle')} description={t('admin.channels.forbiddenDescription')} />;
    }

    return <ErrorState title={t('admin.channels.errorTitle')} description={t('admin.channels.errorDescription')} />;
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.admin')}</span>
          <h2>{t('navigation.channels')}</h2>
          <p>{t('admin.channels.heroDescription')}</p>
        </div>
      </section>

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {channels.length === 0 ? (
            <EmptyState title={t('admin.channels.emptyTitle')} description={t('admin.channels.emptyDescription')} />
          ) : (
            <AdminDataGrid
              title={t('admin.channels.gridTitle')}
              description={t('admin.channels.gridDescription')}
              columns={channelsColumns}
              rows={mapChannelsToRows(channels, selectedChannelId, setSelectedChannelId)}
            />
          )}
        </div>

        <div className="dashboard-page__secondary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.create')}</span>
                <strong>{t('admin.channels.createTitle')}</strong>
              </div>
            </div>

            <form
              className="dashboard-filter-grid"
              onSubmit={addForm.handleSubmit(async (values) => {
                await mutations.add.mutateAsync({ username: values.username });
                addForm.reset();
              })}
            >
              <label>
                <span>{t('fields.username')}</span>
                <input {...addForm.register('username')} placeholder="@channel_name" />
                {addForm.formState.errors.username ? <small>{addForm.formState.errors.username.message}</small> : null}
              </label>
              <div className="dashboard-filter-bar__actions">
                <button type="submit" className="dashboard-button" disabled={mutations.add.isPending}>
                  {t('actions.addChannel')}
                </button>
              </div>
              {mutations.add.data ? <p className="dashboard-panel-copy">{mutations.add.data}</p> : null}
            </form>
          </section>

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.edit')}</span>
                <strong>{selectedChannel ? `@${selectedChannel.username}` : t('admin.channels.selectedChannel')}</strong>
              </div>
            </div>

            {selectedChannel ? (
              <form
                className="dashboard-filter-grid"
                onSubmit={editForm.handleSubmit(async (values) => {
                  await mutations.update.mutateAsync({
                    channelId: selectedChannel.id,
                    payload: {
                      title: values.title || null,
                      category: values.category || null,
                      is_active: values.is_active,
                    },
                  });
                })}
              >
                <label>
                  <span>{t('fields.title')}</span>
                  <input {...editForm.register('title')} />
                </label>
                <label>
                  <span>{t('fields.category')}</span>
                  <input {...editForm.register('category')} />
                </label>
                <label>
                  <span>
                    <input type="checkbox" {...editForm.register('is_active')} />
                    {t('fields.active')}
                  </span>
                </label>
                <div className="dashboard-filter-bar__actions">
                  <button type="submit" className="dashboard-button" disabled={mutations.update.isPending}>
                    {t('actions.saveChannel')}
                  </button>
                  <button
                    type="button"
                    className="dashboard-button dashboard-button--ghost"
                    onClick={async () => {
                      const next = !selectedChannel.is_active;
                      if (!window.confirm(t('admin.channels.confirmToggle', { username: selectedChannel.username }))) {
                        return;
                      }
                      await mutations.setActive.mutateAsync({ channelId: selectedChannel.id, isActive: next });
                    }}
                  >
                    {selectedChannel.is_active ? t('actions.deactivate') : t('actions.activate')}
                  </button>
                  <button
                    type="button"
                    className="dashboard-button dashboard-button--ghost"
                    onClick={async () => {
                      if (!window.confirm(t('admin.channels.confirmDelete', { username: selectedChannel.username }))) {
                        return;
                      }
                      await mutations.remove.mutateAsync(selectedChannel.id);
                    }}
                  >
                    {t('actions.delete')}
                  </button>
                </div>
              </form>
            ) : (
              <p className="dashboard-panel-copy">{t('admin.channels.selectionHint')}</p>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
