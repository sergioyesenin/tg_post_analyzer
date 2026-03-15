import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { RoleAwareNavigation } from '@app/shell/RoleAwareNavigation';
import { TopNavigation } from '@app/shell/TopNavigation';
import { LanguageSwitcher } from '@shared/i18n/LanguageSwitcher';
import { getNavigationItems } from '@shared/routing/policy';

export function AppShell() {
  const { t } = useTranslation();
  const { logout, primaryRole, user } = useSession();
  const roles = user?.roles ?? [];
  const primaryNavigation = [
    { id: 'workspace', to: '/dashboard/posts', label: t('app.workspace') },
    ...getNavigationItems('primary', roles),
  ];

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
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

      <div className="app-main">
        <header className="app-header">
          <div>
            <span className="app-header__label">{t('app.shellLabel')}</span>
            <strong>{t('app.shellDescription')}</strong>
          </div>

          <div className="app-session-chip">
            <LanguageSwitcher />
            <span>{user?.email ?? user?.username ?? t('app.unknownUser')}</span>
            <strong>{primaryRole ?? t('app.guest')}</strong>
            <span>{roles.join(' / ') || t('app.noAccess')}</span>
            <button className="app-session-chip__action" onClick={() => void logout()} type="button">
              {t('actions.logout')}
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
