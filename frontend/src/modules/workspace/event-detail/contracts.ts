export type EventDetailSummaryDto = {
  id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  created_by: string | null;
  comments_count: number;
  involvement: number | null;
};

export type EventDetailDto = {
  event: EventDetailSummaryDto;
  post_ids: number[];
  root_post_id: number | null;
  channels: string[];
};
