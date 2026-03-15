import { useTranslation } from 'react-i18next';
import type { PropsWithChildren } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function AuthGuard({ children }: PropsWithChildren) {
  const { t } = useTranslation();
  const { status } = useSession();
  const location = useLocation();

  if (status === 'bootstrapping') {
    return (
      <LoadingState
        title={t('auth.bootstrap.title', { defaultValue: 'Session bootstrap' })}
        description={t('auth.bootstrap.description', { defaultValue: 'Checking authentication state.' })}
      />
    );
  }

  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }

  return <>{children}</>;
}
