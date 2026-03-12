import type { PropsWithChildren } from 'react';

import { useSession } from '@app/providers/SessionProvider';
import { getRoutePolicy, type RoutePolicyId } from '@shared/routing/policy';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type RoleGuardProps = PropsWithChildren<{
  routeId: RoutePolicyId;
}>;

export function RoleGuard({ routeId, children }: RoleGuardProps) {
  const { hasAnyRole, status, user } = useSession();
  const policy = getRoutePolicy(routeId);

  if (status === 'bootstrapping') {
    return <LoadingState title="Authorizing route" description="Checking role access policy." />;
  }

  if (!user || !hasAnyRole(policy.allowedRoles ?? [])) {
    return (
      <ForbiddenState
        title="Route is restricted"
        description={`Your current role cannot enter ${policy.path}. Hidden navigation and direct route access use the same policy source.`}
      />
    );
  }

  return <>{children}</>;
}
