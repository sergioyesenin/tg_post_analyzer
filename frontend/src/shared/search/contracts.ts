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