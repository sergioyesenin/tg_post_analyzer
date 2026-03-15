import type { PropsWithChildren } from 'react';
import { I18nextProvider } from 'react-i18next';

import { QueryClientProvider } from '@app/providers/QueryClientProvider';
import { SessionProvider } from '@app/providers/SessionProvider';
import { ThemeProvider } from '@app/providers/ThemeProvider';
import { i18n } from '@shared/i18n/i18n';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <I18nextProvider i18n={i18n}>
      <ThemeProvider>
        <QueryClientProvider>
          <SessionProvider>{children}</SessionProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nextProvider>
  );
}
