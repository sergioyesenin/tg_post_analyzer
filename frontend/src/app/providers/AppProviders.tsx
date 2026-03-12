import type { PropsWithChildren } from 'react';

import { QueryClientProvider } from '@app/providers/QueryClientProvider';
import { SessionProvider } from '@app/providers/SessionProvider';
import { ThemeProvider } from '@app/providers/ThemeProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ThemeProvider>
      <QueryClientProvider>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
