import type { PropsWithChildren } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function AuthGuard({ children }: PropsWithChildren) {
  const { status } = useSession();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return <LoadingState title="Session bootstrap" description="Checking authentication state." />;
  }

  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
