import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@shared/api/client';

import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import {
  getPostComments,
  getPostDetail,
  getPostLinks,
  getPostReport,
  getPostReportTrace,
  refreshPostComments,
  updatePostReport,
} from '@modules/workspace/post-detail/api';
import { postDetailQueryKeys } from '@modules/workspace/post-detail/query-keys';

export function usePostDetailQueries(postId: number) {
  const [postQuery, commentsQuery, reportQuery, linksQuery] = useQueries({
    queries: [
      {
        queryKey: postDetailQueryKeys.detail(postId),
        queryFn: () => getPostDetail(postId),
        retry: false,
      },
      {
        queryKey: postDetailQueryKeys.comments(postId),
        queryFn: () => getPostComments(postId),
        retry: false,
      },
      {
        queryKey: postDetailQueryKeys.report(postId),
        queryFn: () => getPostReport(postId),
        retry: false,
      },
      {
        queryKey: postDetailQueryKeys.links(postId),
        queryFn: () => getPostLinks(postId),
        retry: false,
      },
    ],
  });

  return {
    postQuery,
    commentsQuery,
    reportQuery,
    linksQuery,
  };
}

export function useRefreshCommentsAction(postId: number) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Refresh comments',
    mutationFn: () => refreshPostComments(postId),
    onInvalidate: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: postDetailQueryKeys.detail(postId) }),
        queryClient.invalidateQueries({ queryKey: postDetailQueryKeys.comments(postId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('posts') }),
      ]);
    },
  });
}

export function useUpdateReportAction(postId: number) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate or update report',
    mutationFn: () => updatePostReport(postId),
    onInvalidate: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: postDetailQueryKeys.detail(postId) }),
        queryClient.invalidateQueries({ queryKey: postDetailQueryKeys.report(postId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('posts') }),
      ]);
    },
    progress: { mode: 'report-build', entityType: 'post', entityId: postId },
  });
}

export function usePostReportTrace(postId: number) {
  return useQuery({
    queryKey: postDetailQueryKeys.trace(postId),
    queryFn: () => getPostReportTrace(postId),
    retry: (failureCount, error) => {
      // Не ретраить 404 (трейс отсутствует)
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
    staleTime: 5 * 60 * 1000, // 5 минут
    enabled: Number.isFinite(postId) && postId > 0,
  });
}