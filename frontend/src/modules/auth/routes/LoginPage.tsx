import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { getLoginErrorMessage, resolveLoginState } from '@shared/auth/auth-errors';
import { defaultAuthenticatedRoute } from '@shared/routing/policy';
import type { LoginState } from '@shared/auth/session-types';

export function LoginPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { login, status } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginState, setLoginState] = useState<LoginState>('idle');

  const redirectTarget =
    typeof location.state === 'object' &&
    location.state !== null &&
    'from' in location.state &&
    typeof location.state.from === 'string'
      ? location.state.from
      : defaultAuthenticatedRoute;

  if (status === 'authenticated') {
    return <Navigate replace to={redirectTarget} />;
  }

  const errorState =
    loginState === 'invalid_credentials' ||
    loginState === 'service_unavailable' ||
    loginState === 'generic_error'
      ? loginState
      : null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginState('loading');

    try {
      await login({ username, password });
      setLoginState('idle');
      navigate(redirectTarget, { replace: true });
    } catch (error) {
      setLoginState(resolveLoginState(error));
    }
  };

  return (
    <div className="login-shell">
      <section className="login-panel">
        <div className="login-panel__intro">
          <span className="state-card__eyebrow">{t('auth.login.eyebrow', { defaultValue: 'local auth' })}</span>
          <h1 className="login-panel__title">{t('auth.login.title', { defaultValue: 'Sign in to the analytics workspace' })}</h1>
          <p className="login-panel__description">{t('auth.login.description', { defaultValue: 'Sign in to access the shared workspace, reports, and role-based routes.' })}</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="login-form__field">
            <span>{t('fields.username')}</span>
            <input
              autoComplete="username"
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              placeholder={t('auth.login.usernamePlaceholder', { defaultValue: 'admin' })}
              value={username}
            />
          </label>

          <label className="login-form__field">
            <span>{t('fields.password')}</span>
            <input
              autoComplete="current-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t('auth.login.passwordPlaceholder', { defaultValue: '********' })}
              type="password"
              value={password}
            />
          </label>

          {errorState ? <div className="login-form__error">{getLoginErrorMessage(errorState)}</div> : null}

          <button className="login-form__submit" disabled={loginState === 'loading'} type="submit">
            {loginState === 'loading'
              ? t('auth.login.signingIn', { defaultValue: 'Signing in...' })
              : t('auth.login.submit', { defaultValue: 'Sign in' })}
          </button>

          <div className="login-form__meta">
            {redirectTarget !== defaultAuthenticatedRoute
              ? t('auth.login.redirectTarget', {
                  defaultValue: `After sign-in you will be redirected to ${redirectTarget}.`,
                  path: redirectTarget,
                })
              : t('auth.login.redirectDefault', { defaultValue: 'After sign-in the default workspace route will open.' })}
          </div>
        </form>
      </section>
    </div>
  );
}
