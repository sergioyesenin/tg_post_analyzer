export type DashboardMode = 'posts' | 'events' | 'processes';
export type DashboardSeverity = 'info' | 'warning' | 'error';

export type DashboardWarning = {
  code: string;
  message: string;
  severity: DashboardSeverity;
};

export type PartialDashboardState = {
  partial: boolean;
  warnings: DashboardWarning[];
};

export type DashboardSortMeta = {
  by: string;
  order: string;
};

export type DashboardMeta = {
  sort: DashboardSortMeta | null;
  supported_sorts: string[];
};

export type DashboardEnvelope<TMode extends DashboardMode, TSummary, TItem, TFilters> =
  PartialDashboardState & {
    mode: TMode;
    generated_at: string;
    filters_applied: TFilters;
    summary: TSummary;
    items: TItem[];
    meta: DashboardMeta;
  };

export type PostsDashboardFiltersDto = {
  date_from: string;
  date_to: string;
  limit: number;
  channel_ids: number[];
  categories: string[];
  min_comments: number | null;
  report_status: string[];
  sort_by: string;
  sort_order: string;
};

export type PostsDashboardSummaryDto = {
  posts_count: number;
  total_comments: number;
  avg_involvement: number | null;
  channels_count: number;
  reports_ready: number;
  reports_missing: number;
  reports_pending: number;
  reports_failed: number;
};

export type PostsDashboardItemDto = {
  post_id: number;
  channel_id: number;
  channel_username: string | null;
  channel_title: string | null;
  channel_category: string | null;
  date: string;
  text_preview: string | null;
  comments_count: number;
  views: number | null;
  involvement: number | null;
  report_status: string;
  has_report: boolean;
  comments_refresh_available: boolean;
  links_count: number | null;
};

export type PostsDashboardResponse = DashboardEnvelope<
  'posts',
  PostsDashboardSummaryDto,
  PostsDashboardItemDto,
  PostsDashboardFiltersDto
>;

export type EventsDashboardFiltersDto = {
  date_from: string | null;
  date_to: string | null;
  limit: number;
  status: string[];
  channel_ids: number[];
  categories: string[];
  min_comments: number | null;
  sort_by: string;
  sort_order: string;
};

export type EventsDashboardSummaryDto = {
  events_count: number;
  total_linked_posts: number;
  total_comments: number;
  avg_involvement: number | null;
  draft_reports: number;
  ready_reports: number;
  failed_reports: number;
};

export type DashboardChannelRefDto = {
  channel_id: number;
  channel_username: string | null;
};

export type EventsDashboardItemDto = {
  event_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  comments_count: number;
  involvement: number | null;
  posts_count: number;
  post_ids: number[];
  root_post_id: number | null;
  channels: DashboardChannelRefDto[];
  report_status: string;
  graph_ready: boolean;
};

export type EventsDashboardResponse = DashboardEnvelope<
  'events',
  EventsDashboardSummaryDto,
  EventsDashboardItemDto,
  EventsDashboardFiltersDto
>;

export type ProcessesDashboardFiltersDto = {
  date_from: string | null;
  date_to: string | null;
  limit: number;
  status: string[];
  min_comments: number | null;
  sort_by: string;
  sort_order: string;
};

export type ProcessesDashboardSummaryDto = {
  processes_count: number;
  total_events: number;
  total_comments: number;
  avg_involvement: number | null;
  draft_reports: number;
  failed_reports: number;
};

export type ProcessesDashboardItemDto = {
  process_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  comments_count: number;
  involvement: number | null;
  events_count: number;
  event_ids: number[];
  report_status: string;
  graph_ready: boolean;
};

export type ProcessesDashboardResponse = DashboardEnvelope<
  'processes',
  ProcessesDashboardSummaryDto,
  ProcessesDashboardItemDto,
  ProcessesDashboardFiltersDto
>;

export type EventGraphEventDto = {
  event_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  report_status: string;
  posts_count: number;
  comments_count: number;
  involvement: number | null;
};

export type EventGraphNodeDto = {
  post_id: number;
  channel_id: number;
  channel_username: string | null;
  date: string;
  text_preview: string | null;
  comments_count: number;
  views: number | null;
  involvement: number | null;
  is_root: boolean;
};

export type DashboardGraphEdgeDto = {
  link_id: number;
  src_post_id: number;
  dst_post_id: number;
  link_type: string;
  direction: string;
  score: number | null;
  status: string;
};

export type EventGraphResponse = {
  event: EventGraphEventDto;
  nodes: EventGraphNodeDto[];
  edges: DashboardGraphEdgeDto[];
};

export type ProcessGraphSummaryDto = {
  process_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  report_status: string;
  events_count: number;
  posts_count: number;
  comments_count: number;
  involvement: number | null;
};

export type ProcessGraphEventDto = {
  event_id: number;
  title: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  confidence: number | null;
  relation_type: string;
  direction: string;
  score: number | null;
  post_ids: number[];
};

export type ProcessGraphMappingDto = {
  process_id: number;
  event_to_post_ids: Record<number, number[]>;
};

export type ProcessGraphResponse = {
  summary: ProcessGraphSummaryDto;
  events: ProcessGraphEventDto[];
  nodes: EventGraphNodeDto[];
  edges: DashboardGraphEdgeDto[];
  mapping: ProcessGraphMappingDto;
};

export type DashboardTransportResponse =
  | PostsDashboardResponse
  | EventsDashboardResponse
  | ProcessesDashboardResponse;

