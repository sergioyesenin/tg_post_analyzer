import { Outlet } from 'react-router-dom';

export function AnalyticsWorkspaceLayout() {
  return (
    <section className="workspace-layout workspace-layout--analytics">
      <Outlet />
    </section>
  );
}
