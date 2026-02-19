import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export function useChannels() {
  return useQuery({
    queryKey: ["channels"],
    queryFn: async () => (await api.get("/api/channels")).data,
    staleTime: 30_000,
  });
}

export type TopPost = {
  id: number;
  channel_username: string;
  text_preview?: string | null;
  views?: number | null;
  reactions?: number | null;
  comments_count?: number | null;
  score?: number | null;
  published_at?: string | null;
};

export function useTopPosts(params: { fromIsoUtc: string; toIsoUtc: string }) {
  const { fromIsoUtc, toIsoUtc } = params;

  return useQuery({
    queryKey: ["top-posts", fromIsoUtc, toIsoUtc],
    queryFn: async () => {
      const res = await api.get("/api/posts/top", {
        params: { date_from: fromIsoUtc, date_to: toIsoUtc }, 
      });
      return res.data;
    },
    enabled: Boolean(fromIsoUtc && toIsoUtc),
    staleTime: 30_000,
  });
}
