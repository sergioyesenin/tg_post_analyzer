import { NavLink, Outlet } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { getNavigationItems, getRouteCapability } from '@shared/routing/policy';

export function AppShell() {
  const { logout, primaryRole, user } = useSession();
  const roles = user?.roles ?? [];
  const dashboardModes = getNavigationItems('dashboard', roles);
  const primaryNavigation = [
    { id: 'workspace', to: '/dashboard/posts', label: 'Workspace' },
    ...getNavigationItems('primary', roles),
  ];
  const secondaryNavigation = getNavigationItems('secondary', roles);
  const capabilityLabel = getRouteCapability('workspace.posts', primaryRole);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <span className="app-brand__eyebrow">analytics workspace</span>
          <strong>TG Post Analyzer</strong>
        </div>

        <nav className="app-nav" aria-label="Primary">
          {primaryNavigation.map((item) => (
            <NavLink key={item.to} className="app-nav__link" to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <nav className="app-nav app-nav--secondary" aria-label="Operations">
          {secondaryNavigation.map((item) => (
            <NavLink key={item.to} className="app-nav__link" to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div>
            <span className="app-header__label">Dashboard modes</span>
            <div className="app-mode-switcher">
              {dashboardModes.map((mode) => (
                <NavLink key={mode.to} className="app-mode-switcher__item" to={mode.to}>
                  {mode.label}
                </NavLink>
              ))}
            </div>
          </div>

          <div className="app-session-chip">
            <span>{user?.email ?? user?.username ?? 'unknown user'}</span>
            <strong>{primaryRole ?? 'guest'}</strong>
            <span>{capabilityLabel ?? 'no-access'}</span>
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
