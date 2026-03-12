import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderRouteHarness } from '@test/renderRouteHarness';

describe('Guards and placeholders', () => {
  it('shows forbidden state for viewer on admin-only route', async () => {
    renderRouteHarness({
      initialEntry: '/channels',
      bootstrap: async () => ({ id: 'u-3', email: 'viewer@example.com', role: 'viewer' }),
    });

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });
  });

  it('renders non-blocking partial warnings on dashboard placeholder', async () => {
    renderRouteHarness({
      initialEntry: '/dashboard/events',
      bootstrap: async () => ({ id: 'u-4', email: 'analyst@example.com', role: 'analyst' }),
    });

    await waitFor(() => {
      expect(screen.getByText(/Warnings remain non-blocking/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Graph panel implementation is intentionally deferred/i)).toBeInTheDocument();
  });
});
