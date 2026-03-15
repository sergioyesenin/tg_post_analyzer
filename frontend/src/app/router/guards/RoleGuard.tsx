import type { PropsWithChildren } from 'react';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { getRoutePolicy, type RoutePolicyId } from '@shared/routing/policy';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type RoleGuardProps = PropsWithChildren<{
  routeId: RoutePolicyId;
}>;

export function RoleGuard({ routeId, children }: RoleGuardProps) {
  const { t } = useTranslation();
  const { hasAnyRole, status, user } = useSession();
  const policy = getRoutePolicy(routeId);

  if (status === 'bootstrapping') {
    return (
      <LoadingState
        title={t('auth.authorizingRoute.title', { defaultValue: 'Authorizing route' })}
        description={t('auth.authorizingRoute.description', { defaultValue: 'Checking role access policy.' })}
      />
    );
  }

  if (!user || !hasAnyRole(policy.allowedRoles ?? [])) {
    return (
      <ForbiddenState
        title={t('auth.routeRestricted.title', { defaultValue: 'Route is restricted' })}
        description={t('auth.routeRestricted.description', {
          defaultValue: `Your current role cannot enter ${policy.path}. Hidden navigation and direct route access use the same policy source.`,
          path: policy.path,
        })}
      />
    );
  }

  return <>{children}</>;
}
