import { NavLink } from 'react-router-dom';

import type { NavigationSection } from '@shared/routing/policy';
import { getNavigationItems } from '@shared/routing/policy';
import type { UserRole } from '@shared/auth/roles';

type RoleAwareNavigationProps = {
  section: NavigationSection;
  roles: readonly UserRole[];
  ariaLabel: string;
  className?: string;
};

export function RoleAwareNavigation({ section, roles, ariaLabel, className }: RoleAwareNavigationProps) {
  const items = getNavigationItems(section, roles);

  return (
    <nav className={className} aria-label={ariaLabel}>
      {items.map((item) => (
        <NavLink key={item.to} className="app-nav__link" to={item.to}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
