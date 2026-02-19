import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type PostFullOut = {
  id: number;
  text: string | null;
};

export type CommentOut = {
  id: number;
  text: string | null;
  author?: string | null;
  date?: string | null;
};

export type ReportOut = {
  id: number;
  content: string | null; // подстрой под своё поле
};

export function usePostFull(postId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["post-full", postId],
    queryFn: async () => (await api.get<PostFullOut>(`/api/posts/${postId}`)).data,
    enabled,
    staleTime: 60_000,
  });
}

export function usePostComments(postId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["post-comments", postId],
    queryFn: async () =>
      (await api.get<CommentOut[]>(`/api/posts/${postId}/comments`)).data,
    enabled,
    staleTime: 30_000,
  });
}

export function usePostReport(postId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["post-report", postId],
    queryFn: async () =>
      (await api.get<ReportOut>(`/api/reports/${postId}`)).data,
    enabled,
    staleTime: 30_000,
  });
}
