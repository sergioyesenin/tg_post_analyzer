import { describe, expect, it, vi } from 'vitest';

import { ApiClient } from '@shared/api/client';

describe('Refresh flow', () => {
  it('retries a protected request once after successful token refresh', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    const client = new ApiClient({ fetchImpl: fetchMock as typeof fetch });
    const refreshAccessToken = vi.fn().mockResolvedValue('fresh-access');

    client.configureAuth({
      getAccessToken: () => 'expired-access',
      refreshAccessToken,
    });

    const response = await client.get<{ ok: boolean }>('/api/protected');

    expect(response.ok).toBe(true);
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
