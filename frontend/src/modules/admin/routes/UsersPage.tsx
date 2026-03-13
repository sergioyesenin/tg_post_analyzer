import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

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
    return <LoadingState title="Loading users" description="Fetching user administration data." />;
  }

  if (usersQuery.isError) {
    const error = usersQuery.error;
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title="Users module is restricted" description="Your role cannot access user administration." />;
    }

    return <ErrorState title="Users failed to load" description="The users list request failed." />;
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">admin</span>
          <h2>Users</h2>
          <p>Admin-only user management with create, role update and active state flows.</p>
        </div>
      </section>

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {users.length === 0 ? (
            <EmptyState title="No users available" description="The users endpoint returned an empty list." />
          ) : (
            <AdminDataGrid
              title="Users grid"
              description="User administration grid with stable selection."
              columns={usersColumns}
              rows={mapUsersToRows(users, selectedUserId, setSelectedUserId)}
            />
          )}
        </div>

        <div className="dashboard-page__secondary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">create</span>
                <strong>Create user</strong>
              </div>
            </div>

            <form
              className="dashboard-filter-grid"
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
              <label>
                <span>Username</span>
                <input {...createForm.register('username')} />
              </label>
              <label>
                <span>Password</span>
                <input type="password" {...createForm.register('password')} />
              </label>
              <label>
                <span>Email</span>
                <input {...createForm.register('email')} />
              </label>
              <label>
                <span>Full name</span>
                <input {...createForm.register('full_name')} />
              </label>
              <fieldset>
                <legend>Roles</legend>
                {availableRoles.map((role) => (
                  <label key={role}>
                    <span>
                      <input type="checkbox" value={role} {...createForm.register('roles')} />
                      {role}
                    </span>
                  </label>
                ))}
              </fieldset>
              <div className="dashboard-filter-bar__actions">
                <button type="submit" className="dashboard-button" disabled={mutations.create.isPending}>
                  Create user
                </button>
              </div>
            </form>
          </section>

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">edit</span>
                <strong>{selectedUser ? selectedUser.username : 'Selected user'}</strong>
              </div>
            </div>

            {selectedUser ? (
              <form
                className="dashboard-filter-grid"
                onSubmit={rolesForm.handleSubmit(async (values) => {
                  if (!window.confirm(`Update roles for ${selectedUser.username}?`)) {
                    return;
                  }
                  await mutations.updateRoles.mutateAsync({ userId: selectedUser.id, payload: { roles: values.roles } });
                })}
              >
                <fieldset>
                  <legend>Roles</legend>
                  {availableRoles.map((role) => (
                    <label key={role}>
                      <span>
                        <input type="checkbox" value={role} {...rolesForm.register('roles')} />
                        {role}
                      </span>
                    </label>
                  ))}
                </fieldset>
                {rolesForm.formState.errors.roles ? <small>{rolesForm.formState.errors.roles.message}</small> : null}
                <div className="dashboard-filter-bar__actions">
                  <button type="submit" className="dashboard-button" disabled={mutations.updateRoles.isPending}>
                    Save roles
                  </button>
                  <button
                    type="button"
                    className="dashboard-button dashboard-button--ghost"
                    onClick={async () => {
                      const nextActive = !selectedUser.is_active;
                      if (!window.confirm(`Change active status for ${selectedUser.username}?`)) {
                        return;
                      }
                      await mutations.setActive.mutateAsync({ userId: selectedUser.id, active: nextActive });
                    }}
                  >
                    {selectedUser.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </form>
            ) : (
              <p className="dashboard-panel-copy">Select a user row to update roles and active state.</p>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
