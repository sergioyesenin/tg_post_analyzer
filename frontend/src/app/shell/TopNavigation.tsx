import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

type TopNavigationProps = {
  items: Array<{
    id: string;
    to: string;
    label: string;
  }>;
};

export function TopNavigation({ items }: TopNavigationProps) {
  const { t } = useTranslation();

  return (
    <nav className="app-top-navigation" aria-label={t('navigation.top')}>
      {items.map((item) => (
        <NavLink key={item.id} className="app-top-navigation__link" to={item.to}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
