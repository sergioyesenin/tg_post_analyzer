import { Outlet } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { RoleAwareNavigation } from '@app/shell/RoleAwareNavigation';
import { TopNavigation } from '@app/shell/TopNavigation';
import { getNavigationItems } from '@shared/routing/policy';

export function AppShell() {
  const { logout, primaryRole, user } = useSession();
  const roles = user?.roles ?? [];
  const primaryNavigation = [
    { id: 'workspace', to: '/dashboard/posts', label: 'Workspace' },
    ...getNavigationItems('primary', roles),
  ];

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <span className="app-brand__eyebrow">analytics workspace</span>
          <strong>TG Post Analyzer</strong>
        </div>

        <TopNavigation items={primaryNavigation} />

        <RoleAwareNavigation section="secondary" roles={roles} ariaLabel="Operations" className="app-nav app-nav--secondary" />
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div>
            <span className="app-header__label">Workspace shell</span>
            <strong>Role-aware navigation and dashboard modules</strong>
          </div>

          <div className="app-session-chip">
            <span>{user?.email ?? user?.username ?? 'unknown user'}</span>
            <strong>{primaryRole ?? 'guest'}</strong>
            <span>{roles.join(' / ') || 'no-access'}</span>
            <button className="app-session-chip__action" onClick={() => void logout()} type="button">
              Logout
            </button>
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
