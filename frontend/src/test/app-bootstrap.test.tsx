import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { SessionUser } from '@shared/auth/session-types';
import { renderRouteHarness } from '@test/renderRouteHarness';

describe('App bootstrap', () => {
  it('renders the protected shell after session bootstrap succeeds', async () => {
    let resolveBootstrap: ((value: SessionUser | null) => void) | undefined;
    const bootstrap = () =>
      new Promise<SessionUser | null>((resolve) => {
        resolveBootstrap = resolve;
      });

    renderRouteHarness({ initialEntry: '/dashboard/posts', bootstrap });

    expect(screen.getByText(/session bootstrap/i)).toBeInTheDocument();

    if (!resolveBootstrap) {
      throw new Error('Session bootstrap resolver was not initialized.');
    }

    resolveBootstrap({ id: 'u-1', email: 'admin@example.com', role: 'admin' });

    await waitFor(() => {
      expect(screen.getByText(/TG Post Analyzer/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Posts dashboard foundation/i)).toBeInTheDocument();
  });
});
