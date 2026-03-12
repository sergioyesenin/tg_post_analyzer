import type { PropsWithChildren } from 'react';
import { useState } from 'react';
import { QueryClient, QueryClientProvider as ReactQueryClientProvider } from '@tanstack/react-query';

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
}

export function QueryClientProvider({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);

  return <ReactQueryClientProvider client={queryClient}>{children}</ReactQueryClientProvider>;
}
