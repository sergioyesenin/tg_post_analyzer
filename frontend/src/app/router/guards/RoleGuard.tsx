import type { PropsWithChildren } from 'react';

import { useSession } from '@app/providers/SessionProvider';
import type { UserRole } from '@shared/auth/roles';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type RoleGuardProps = PropsWithChildren<{
  allowedRoles: UserRole[];
}>;

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { hasAnyRole, status, user } = useSession();

  if (status === 'bootstrapping') {
    return <LoadingState title="Authorizing route" description="Checking role access policy." />;
  }

  if (!user || !hasAnyRole(allowedRoles)) {
    return (
      <ForbiddenState
        title="Route is restricted"
        description="This placeholder route is wired, but your current role cannot enter it."
      />
    );
  }

  return <>{children}</>;
}
