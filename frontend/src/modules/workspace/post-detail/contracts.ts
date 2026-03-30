import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export type PostDetailDto = {
  id: number;
  channel_id: number;
  text: string | null;
  date: string;
  comments_count: number;
  views: number | null;
  involvement: number | null;
};

export type CommentDto = {
  id: number;
  post_id: number;
  tg_message_id: number;
  parent_tg_message_id: number | null;
  parent_comment_id: number | null;
  thread_root_tg_message_id: number | null;
  depth: number;
  text: string;
  date: string;
};

export type ReportDto = {
  id: number;
  post_id: number;
  status: string;
  content: string | null;
  report_json: Record<string, unknown> | null;
  created_at: string;
};

export type LinkDto = {
  id: number;
  src_post_id: number;
  dst_post_id: number;
  link_type: string;
  direction: string;
  score: number | null;
  status: string;
  evidence_json: Record<string, unknown> | null;
  model_version: string | null;
  pipeline_version: string | null;
  created_at: string;
  updated_at: string;
};

export type PostLinksDto = {
  post_id: number;
  links: LinkDto[];
};

export type PostDetailQueryBundle = {
  post: PostDetailDto;
  comments: CommentDto[];
  report: ReportDto | null;
  links: PostLinksDto;
};

export type PostDetailMutationResponse = AcceptedJobResponse;

