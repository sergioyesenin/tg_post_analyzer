import { Navigate } from 'react-router-dom';

import { defaultAuthenticatedRoute } from '@shared/routing/policy';

export function RootRedirect() {
  return <Navigate to={defaultAuthenticatedRoute} replace />;
}
