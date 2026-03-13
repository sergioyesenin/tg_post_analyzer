export const keywordGraphQueryKeys = {
  all: ['keyword-graph'] as const,
  channels: () => [...keywordGraphQueryKeys.all, 'channels'] as const,
  search: (query: string) => [...keywordGraphQueryKeys.all, 'search', query] as const,
};
