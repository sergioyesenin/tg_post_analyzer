import { ApiError, apiClient } from '@shared/api/client';
import type {
  CommentDto,
  PostDetailDto,
  PostDetailMutationResponse,
  PostLinksDto,
  ReportDto,
} from '@modules/workspace/post-detail/contracts';

export function getPostDetail(postId: number) {
  return apiClient.get<PostDetailDto>(`/api/posts/${postId}`);
}

export function getPostComments(postId: number) {
  return apiClient.get<CommentDto[]>(`/api/posts/${postId}/comments`);
}

export async function getPostReport(postId: number) {
  try {
    return await apiClient.get<ReportDto>(`/api/reports/post/${postId}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}

export function getPostLinks(postId: number) {
  return apiClient.get<PostLinksDto>(`/api/posts/${postId}/links`);
}

export function refreshPostComments(postId: number) {
  return apiClient.post<PostDetailMutationResponse>(`/api/posts/${postId}/comments/update`);
}

export function updatePostReport(postId: number) {
  return apiClient.post<PostDetailMutationResponse>(`/api/reports/post/${postId}/update`);
}
