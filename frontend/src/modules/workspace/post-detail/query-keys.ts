export const postDetailQueryKeys = {
  all: ['post-detail'] as const,
  detail: (postId: number) => [...postDetailQueryKeys.all, postId, 'detail'] as const,
  comments: (postId: number) => [...postDetailQueryKeys.all, postId, 'comments'] as const,
  report: (postId: number) => [...postDetailQueryKeys.all, postId, 'report'] as const,
  links: (postId: number) => [...postDetailQueryKeys.all, postId, 'links'] as const,
  trace: (postId: number) => [...postDetailQueryKeys.all, postId, 'trace'] as const,
} as const;
