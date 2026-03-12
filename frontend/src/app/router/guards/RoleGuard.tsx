import type { PropsWithChildren } from 'react';

import { useSession } from '@app/providers/SessionProvider';
import type { UserRole } from '@shared/auth/roles';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';

type RoleGuardProps = PropsWithChildren<{
  allowedRoles: UserRole[];
}>;

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { user } = useSession();

  if (!user || !allowedRoles.includes(user.role)) {
    return (
      <ForbiddenState
        title="Route is restricted"
        description="This placeholder route is wired, but your current role cannot enter it."
      />
    );
  }

  return <>{children}</>;
}
