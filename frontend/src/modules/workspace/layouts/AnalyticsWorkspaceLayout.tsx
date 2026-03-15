import { Outlet, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
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

export function AnalyticsWorkspaceLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useSession();
  const currentMode = resolveCurrentMode(location.pathname);
  const modeTitleMap: Record<DashboardMode, string> = {
    posts: t('navigation.posts'),
    events: t('navigation.events'),
    processes: t('navigation.processes'),
  };

  return (
    <section className="workspace-layout">
      <header className="workspace-layout__header">
        <div>
          <span className="state-card__eyebrow">{t('app.brandEyebrow')}</span>
          <h1>{t('workspace.headerTitle', { mode: modeTitleMap[currentMode], defaultValue: `${modeTitleMap[currentMode]} dashboard` })}</h1>
          <p>{t('workspace.headerDescription', { defaultValue: 'One workspace shell, role-aware mode navigation and URL-owned dashboard state.' })}</p>
        </div>

        <div className="workspace-layout__header-meta">
          <DashboardModeSwitcher currentMode={currentMode} roles={user?.roles ?? []} />
          <div className="workspace-layout__header-note">
            {t('workspace.headerNote', { defaultValue: 'Common filters survive mode switches only when the target mode supports them.' })}
          </div>
        </div>
      </header>

      <Outlet />
    </section>
  );
}
