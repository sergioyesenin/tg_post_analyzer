import { FormEvent, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { getLoginErrorMessage, resolveLoginState } from '@shared/auth/auth-errors';
import type { LoginState } from '@shared/auth/session-types';

export function LoginPage() {
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
      : '/dashboard/posts';

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
          <span className="state-card__eyebrow">local auth</span>
          <h1 className="login-panel__title">Авторизация в аналитическом контуре</h1>
          <p className="login-panel__description">
            Вход открывает доступ к рабочему пространству мониторинга, отчетам и role-based маршрутам.
          </p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="login-form__field">
            <span>Username</span>
            <input
              autoComplete="username"
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
              value={username}
            />
          </label>

          <label className="login-form__field">
            <span>Password</span>
            <input
              autoComplete="current-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              type="password"
              value={password}
            />
          </label>

          {errorState ? <div className="login-form__error">{getLoginErrorMessage(errorState)}</div> : null}

          <button className="login-form__submit" disabled={loginState === 'loading'} type="submit">
            {loginState === 'loading' ? 'Выполняется вход…' : 'Войти'}
          </button>

          <div className="login-form__meta">
            {redirectTarget !== '/dashboard/posts'
              ? `После входа будет открыт маршрут: ${redirectTarget}`
              : 'После входа откроется основное рабочее пространство.'}
          </div>
        </form>
      </section>
    </div>
  );
}
