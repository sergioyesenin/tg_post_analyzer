import { Outlet, useLocation } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import type { DashboardMode } from '@shared/dashboard/contracts';
import { DashboardModeSwitcher } from '@modules/workspace/components/DashboardModeSwitcher';

const modeTitleMap: Record<DashboardMode, string> = {
  posts: 'Posts',
  events: 'Events',
  processes: 'Processes',
};

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
  const location = useLocation();
  const { user } = useSession();
  const currentMode = resolveCurrentMode(location.pathname);

  return (
    <section className="workspace-layout">
      <header className="workspace-layout__header">
        <div>
          <span className="state-card__eyebrow">analytics workspace</span>
          <h1>{modeTitleMap[currentMode]} dashboard</h1>
          <p>One workspace shell, role-aware mode navigation and URL-owned dashboard state.</p>
        </div>

        <div className="workspace-layout__header-meta">
          <DashboardModeSwitcher currentMode={currentMode} roles={user?.roles ?? []} />
          <div className="workspace-layout__header-note">Common filters survive mode switches only when the target mode supports them.</div>
        </div>
      </header>

      <Outlet />
    </section>
  );
}
