import { NavLink } from 'react-router-dom';

type TopNavigationProps = {
  items: Array<{
    id: string;
    to: string;
    label: string;
  }>;
};

export function TopNavigation({ items }: TopNavigationProps) {
  return (
    <nav className="app-top-navigation" aria-label="Top navigation">
      {items.map((item) => (
        <NavLink key={item.id} className="app-top-navigation__link" to={item.to}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
