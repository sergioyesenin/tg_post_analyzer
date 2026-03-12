import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderRouteHarness } from '@test/renderRouteHarness';

describe('Routing shell', () => {
  it('redirects root to dashboard/posts for authenticated users', async () => {
    renderRouteHarness({
      initialEntry: '/',
      bootstrap: async () => ({ id: 'u-2', email: 'analyst@example.com', role: 'analyst' }),
    });

    await waitFor(() => {
      expect(screen.getByText(/Posts dashboard foundation/i)).toBeInTheDocument();
    });
  });

  it('redirects guests to login', async () => {
    renderRouteHarness({ initialEntry: '/dashboard/events', bootstrap: async () => null });

    await waitFor(() => {
      expect(screen.getByText(/Login route placeholder/i)).toBeInTheDocument();
    });
  });
});
