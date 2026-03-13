import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export type ReportType = 'posts' | 'events' | 'processes';

export type PostReportListItemDto = {
  report_id: number;
  post_id: number;
  status: string;
  created_at: string | null;
  post_date: string | null;
  channel_id: number;
  channel_username: string | null;
  channel_category: string | null;
};

export type EventReportListItemDto = {
  report_id: number;
  event_id: number;
  event_title: string | null;
  status: string;
  version: string | null;
  created_at: string | null;
};

export type ProcessReportListItemDto = {
  report_id: number;
  process_id: number;
  process_title: string | null;
  status: string;
  version: string | null;
  created_at: string | null;
};

export type ReportsListResponseByType = {
  posts: PostReportListItemDto[];
  events: EventReportListItemDto[];
  processes: ProcessReportListItemDto[];
};

export type ReportsExportResponseByType = {
  posts: {
    total: number;
    items: Array<PostReportListItemDto & { content: string | null }>;
  };
  events: {
    total: number;
    items: Array<EventReportListItemDto & { report_text: string | null }>;
  };
  processes: {
    total: number;
    items: Array<ProcessReportListItemDto & { report_text: string | null }>;
  };
};

export type ReportsFiltersByType = {
  posts: {
    channel_ids: number[];
    categories: string[];
    date_from: string;
    date_to: string;
    min_comments: number | null;
    limit: number;
    offset: number;
  };
  events: {
    event_id: number | null;
    date_from: string;
    date_to: string;
    limit: number;
    offset: number;
  };
  processes: {
    process_id: number | null;
    date_from: string;
    date_to: string;
    limit: number;
    offset: number;
  };
};

export type PostReportBatchMutationResponse = AcceptedJobResponse;
