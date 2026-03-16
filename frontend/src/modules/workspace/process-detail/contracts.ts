export type ProcessDetailSummaryDto = {
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

export type ProcessDetailEventDto = {
  event_id: number;
  title: string | null;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  relation_type: string;
  direction: string;
  score: number | null;
  status: string;
  post_ids: number[];
};

export type ProcessDetailDto = {
  process: ProcessDetailSummaryDto;
  events: ProcessDetailEventDto[];
};
