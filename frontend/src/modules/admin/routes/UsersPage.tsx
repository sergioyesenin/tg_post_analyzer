import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { useUserMutations, useUsersQuery } from '@modules/admin/hooks';
import { mapUsersToRows, usersColumns } from '@modules/admin/mappers';
import {
  createUserSchema,
  type CreateUserFormValues,
  updateUserRolesSchema,
  type UpdateUserRolesFormValues,
} from '@modules/admin/validation';
import { ApiError } from '@shared/api/client';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

const availableRoles = ['admin', 'analyst', 'viewer'] as const;

export function UsersPage() {
  const { t } = useTranslation();
  const usersQuery = useUsersQuery();
  const mutations = useUserMutations();
  const users = usersQuery.data ?? [];
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const selectedUser = users.find((user) => user.id === selectedUserId) ?? null;

  useEffect(() => {
    if (users.length === 0) {
      setSelectedUserId(null);
      return;
    }

    setSelectedUserId((current) => (current && users.some((user) => user.id === current) ? current : users[0]!.id));
  }, [users]);

  const createForm = useForm<CreateUserFormValues>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      username: '',
      password: '',
      email: '',
      full_name: '',
      roles: ['analyst'],
    },
  });

  const rolesForm = useForm<UpdateUserRolesFormValues>({
    resolver: zodResolver(updateUserRolesSchema),
    values: {
      roles: selectedUser?.roles.filter((role): role is 'admin' | 'analyst' | 'viewer' => availableRoles.includes(role as never)) ?? [],
    },
  });

  if (usersQuery.isLoading) {
    return <LoadingState title={t('admin.users.loadingTitle')} description={t('admin.users.loadingDescription')} />;
  }

  if (usersQuery.isError) {
    const error = usersQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('admin.users.forbiddenTitle')} description={t('admin.users.forbiddenDescription')} />;
    }

    return <ErrorState title={t('admin.users.errorTitle')} description={t('admin.users.errorDescription')} />;
  }

  const isEditBusy = mutations.updateRoles.isPending || mutations.setActive.isPending;

  return (
    <div className="dashboard-page admin-console-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.admin')}</span>
          <h2>{t('navigation.users')}</h2>
          <p>{t('admin.users.heroDescription')}</p>
        </div>
      </section>

      <section className="dashboard-page__content dashboard-page__content--workspace admin-console-page__content">
        <div className="dashboard-page__primary">
          {users.length === 0 ? (
            <EmptyState title={t('admin.users.emptyTitle')} description={t('admin.users.emptyDescription')} />
          ) : (
            <AdminDataGrid
              title={t('admin.users.gridTitle')}
              description={t('admin.users.gridDescription')}
              columns={usersColumns}
              rows={mapUsersToRows(users, selectedUserId, setSelectedUserId)}
            />
          )}
        </div>

        <div className="dashboard-page__secondary admin-console-page__rail">
          <section className="detail-block admin-console-card">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.create')}</span>
                <strong>{t('admin.users.createTitle')}</strong>
              </div>
            </div>

            <form
              className="dashboard-filter-grid admin-console-form"
              onSubmit={createForm.handleSubmit(async (values) => {
                await mutations.create.mutateAsync({
                  username: values.username,
                  password: values.password,
                  email: values.email || null,
                  full_name: values.full_name || null,
                  roles: values.roles,
                });
                createForm.reset({ username: '', password: '', email: '', full_name: '', roles: ['analyst'] });
              })}
            >
              <label className="admin-console-form__field">
                <span>{t('fields.username')}</span>
                <input {...createForm.register('username')} />
              </label>
              <label className="admin-console-form__field">
                <span>{t('fields.password')}</span>
                <input type="password" {...createForm.register('password')} />
              </label>
              <label className="admin-console-form__field">
                <span>{t('fields.email')}</span>
                <input {...createForm.register('email')} />
              </label>
              <label className="admin-console-form__field">
                <span>{t('fields.fullName')}</span>
                <input {...createForm.register('full_name')} />
              </label>
              <fieldset className="admin-console-form__fieldset">
                <legend>{t('fields.roles')}</legend>
                <div className="admin-console-form__checkbox-list">
                  {availableRoles.map((role) => (
                    <label key={role} className="admin-console-form__checkbox">
                      <input type="checkbox" value={role} {...createForm.register('roles')} />
                      <span>{t(`admin.roles.${role}`)}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="dashboard-filter-bar__actions admin-console-actions">
                <button type="submit" className="admin-console-button admin-console-button--secondary" disabled={mutations.create.isPending}>
                  {t('actions.createUser')}
                </button>
              </div>
            </form>
          </section>

          <section className="detail-block admin-console-card">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.edit')}</span>
                <strong>{selectedUser ? selectedUser.username : t('admin.users.selectedUser')}</strong>
              </div>
            </div>

            {selectedUser ? (
              <form
                className="dashboard-filter-grid admin-console-form"
                onSubmit={rolesForm.handleSubmit(async (values) => {
                  if (!window.confirm(t('admin.users.confirmRoles', { username: selectedUser.username }))) {
                    return;
                  }
                  await mutations.updateRoles.mutateAsync({ userId: selectedUser.id, payload: { roles: values.roles } });
                })}
              >
                <fieldset className="admin-console-form__fieldset">
                  <legend>{t('fields.roles')}</legend>
                  <div className="admin-console-form__checkbox-list">
                    {availableRoles.map((role) => (
                      <label key={role} className="admin-console-form__checkbox">
                        <input type="checkbox" value={role} {...rolesForm.register('roles')} />
                        <span>{t(`admin.roles.${role}`)}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                {rolesForm.formState.errors.roles ? <small>{rolesForm.formState.errors.roles.message}</small> : null}
                <div className="dashboard-filter-bar__actions admin-console-actions">
                  <button type="submit" className="admin-console-button admin-console-button--primary" disabled={isEditBusy}>
                    {t('actions.saveRoles')}
                  </button>
                  <button
                    type="button"
                    className="admin-console-button admin-console-button--secondary"
                    disabled={isEditBusy}
                    onClick={async () => {
                      const nextActive = !selectedUser.is_active;
                      if (!window.confirm(t('admin.users.confirmToggle', { username: selectedUser.username }))) {
                        return;
                      }
                      await mutations.setActive.mutateAsync({ userId: selectedUser.id, active: nextActive });
                    }}
                  >
                    {selectedUser.is_active ? t('actions.deactivate') : t('actions.activate')}
                  </button>
                </div>
              </form>
            ) : (
              <p className="dashboard-panel-copy">{t('admin.users.selectionHint')}</p>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
