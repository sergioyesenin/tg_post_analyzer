import { Outlet, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { TopNavigation } from '@app/shell/TopNavigation';
import { RoleAwareNavigation } from '@app/shell/RoleAwareNavigation';
import { LanguageSwitcher } from '@shared/i18n/LanguageSwitcher';
import { getNavigationItems } from '@shared/routing/policy';
import type { DashboardMode } from '@shared/dashboard/contracts';
import { DashboardModeSwitcher } from '@modules/workspace/components/DashboardModeSwitcher';

function resolveCurrentMode(pathname: string): DashboardMode {
  if (pathname.startsWith('/dashboard/events')) {
    return 'events';
  }

  if (pathname.startsWith('/dashboard/processes')) {
    return 'processes';
  }

  return 'posts';
}

export function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const { logout, primaryRole, user } = useSession();
  const roles = user?.roles ?? [];
  const isDashboardRoute = location.pathname.startsWith('/dashboard');
  const isAnalyticsRoute =
    isDashboardRoute ||
    location.pathname.startsWith('/reports') ||
    location.pathname.startsWith('/keyword-graph');
  const currentMode = resolveCurrentMode(location.pathname);
  const modeTitleMap: Record<DashboardMode, string> = {
    posts: t('navigation.posts'),
    events: t('navigation.events'),
    processes: t('navigation.processes'),
  };
  const primaryNavigation = [
    { id: 'workspace', to: '/dashboard/posts', label: t('app.workspace') },
    ...getNavigationItems('primary', roles),
  ];

  return (
    <div className={`app-shell ${isAnalyticsRoute ? 'app-shell--analytics' : ''}`.trim()}>
      <aside className="app-sidebar">
        <div
          className={`app-session-chip ${isAnalyticsRoute ? 'app-session-chip--compact' : ''}`.trim()}
        >
          <div className="app-session-chip__row app-session-chip__row--primary">
            <LanguageSwitcher />
            <strong className="app-session-chip__role">{primaryRole ?? t('app.guest')}</strong>
          </div>

          <div className="app-session-chip__row app-session-chip__row--secondary">
            <span className="app-session-chip__meta">{roles.join(' / ') || t('app.noAccess')}</span>
            <button className="app-session-chip__action" onClick={() => void logout()} type="button">
              {t('actions.logout')}
            </button>
          </div>
        </div>

        <div className="app-brand">
          <span className="app-brand__eyebrow">{t('app.brandEyebrow')}</span>
          <strong>{t('app.name')}</strong>
        </div>

        <TopNavigation items={primaryNavigation} />

        <RoleAwareNavigation
          section="secondary"
          roles={roles}
          ariaLabel="navigation.operations"
          className="app-nav app-nav--secondary"
        />
      </aside>

      <div className={`app-main ${isAnalyticsRoute ? 'app-main--analytics' : ''}`.trim()}>
        

          {isDashboardRoute ? (
            <div className="app-header__intro app-header__intro--analytics-dashboard">
              <span className="app-header__label">{t('app.brandEyebrow')}</span>
              <h1>
                {t('workspace.headerTitle', {
                  mode: modeTitleMap[currentMode],
                  defaultValue: `${modeTitleMap[currentMode]} dashboard`,
                })}
              </h1>
            </div>
          ) : null}

          {isDashboardRoute ? (
            <div
              className="app-header__mode-switch"
              aria-label={t('navigation.dashboardModeSwitcher')}
            >
              <DashboardModeSwitcher currentMode={currentMode} roles={roles} />
            </div>
          ) : null}
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
