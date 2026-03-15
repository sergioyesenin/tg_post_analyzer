import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import { getDashboardModePath, getModeSwitchSearch } from '@shared/dashboard/filters';
import { getNavigationItems } from '@shared/routing/policy';
import type { UserRole } from '@shared/auth/roles';

type DashboardModeSwitcherProps = {
  currentMode: DashboardMode;
  roles: readonly UserRole[];
};

export function DashboardModeSwitcher({ currentMode, roles }: DashboardModeSwitcherProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const dashboardModes = getNavigationItems('dashboard', roles);

  return (
    <div className="workspace-mode-switcher" aria-label={t('navigation.dashboardModeSwitcher')}>
      {dashboardModes.map((mode) => {
        const nextMode = mode.id.replace('workspace.', '') as DashboardMode;

        return (
          <NavLink
            key={mode.id}
            className="workspace-mode-switcher__item"
            to={{
              pathname: getDashboardModePath(nextMode),
              search: getModeSwitchSearch(currentMode, nextMode, location.search),
            }}
          >
            {mode.label}
          </NavLink>
        );
      })}
    </div>
  );
}
