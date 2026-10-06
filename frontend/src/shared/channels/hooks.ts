import { useQuery } from '@tanstack/react-query';

import { getChannels } from '@shared/channels/api';

export const sharedChannelsQueryKeys = {
  all: ['channels'] as const,
  list: () => [...sharedChannelsQueryKeys.all, 'list'] as const,
};

export function useChannelsQuery() {
  return useQuery({
    queryKey: sharedChannelsQueryKeys.list(),
    queryFn: getChannels,
    retry: false,
  });
}