export type KeywordSearchFilters = {
  query: string;
  limit: number;
  date_from: string;
  date_to: string;
  channel_ids: number[];
};

export type KeywordSearchItemDto = {
  post_id: number;
  channel_id: number;
  channel_username: string | null;
  date: string;
  text_preview: string | null;
  comments_count: number;
  views: number | null;
  involvement: number | null;
  rank: number;
  matched_lemmas: string[];
};

export type KeywordSearchResponseDto = {
  query: string;
  normalized_query: string;
  lemmas: string[];
  took_ms: number;
  total: number;
  items: KeywordSearchItemDto[];
};

export type KeywordGraphBuildRequest = {
  post_ids: number[];
  exclude_post_ids: number[];
  graph_mode?: 'transient' | 'persisted';
  include_neighbors?: boolean;
  neighbor_depth?: number;
};

export type KeywordGraphNodeDto = {
  post_id: number;
  channel_id: number;
  channel_username: string | null;
  date: string;
  text_preview: string | null;
  comments_count: number;
  views: number | null;
  involvement: number | null;
  included_by: string;
};

export type KeywordGraphEdgeDto = {
  link_id: number;
  src_post_id: number;
  dst_post_id: number;
  link_type: string;
  direction: string;
  score: number | null;
  status: string;
  edge_source: string;
  evidence: Record<string, unknown> | null;
};

export type KeywordGraphBuildResponseDto = {
  seed_post_ids: number[];
  excluded_post_ids: number[];
  nodes: KeywordGraphNodeDto[];
  edges: KeywordGraphEdgeDto[];
  took_ms: number;
  meta: Record<string, unknown>;
};

export type KeywordGraphReportRequest = KeywordGraphBuildRequest & {
  title?: string;
};

export type KeywordGraphReportResponseDto = {
  status: string;
  title: string;
  post_ids: number[];
  excluded_post_ids: number[];
  content: string;
};

export type KeywordGraphConfig = {
  graph_mode: 'transient' | 'persisted';
  include_neighbors: boolean;
  neighbor_depth: number;
};
