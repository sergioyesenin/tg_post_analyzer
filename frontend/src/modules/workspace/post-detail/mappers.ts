import type {
  CommentDto,
  LinkDto,
  PostDetailDto,
  PostDetailQueryBundle,
  ReportDto,
} from '@modules/workspace/post-detail/contracts';
import { i18n } from '@shared/i18n/i18n';

export type PostDetailViewModel = {
  id: number;
  text: string;
  date: string;
  commentsCount: string;
  views: string;
  involvement: string;
};

export type CommentViewModel = {
  id: number;
  tgMessageId: number;
  depth: number;
  date: string;
  text: string;
  parentCommentId: number | null;
  threadRootMessageId: number | null;
  threadModeHint: boolean;
};

export type ReportViewModel = {
  id: number;
  status: string;
  content: string;
  createdAt: string;
  summary: string | null;
  topics: string[];
};

export type LinkViewModel = {
  id: number;
  route: string;
  type: string;
  direction: string;
  score: string;
  status: string;
  updatedAt: string;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(i18n.language === 'ru' ? 'ru' : 'en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatNullableNumber(value: number | null) {
  return value === null ? i18n.t('common.na') : new Intl.NumberFormat(i18n.language === 'ru' ? 'ru' : 'en').format(value);
}

function formatNullableRatio(value: number | null) {
  return value === null ? i18n.t('common.na') : value.toFixed(2);
}

function readReportSummary(reportJson: Record<string, unknown> | null): string | null {
  if (!reportJson) {
    return null;
  }
  const summary = reportJson.summary;
  return typeof summary === 'string' && summary.trim() ? summary : null;
}

function readReportTopics(reportJson: Record<string, unknown> | null): string[] {
  if (!reportJson) {
    return [];
  }
  const topics = reportJson.topics;
  if (!Array.isArray(topics)) {
    return [];
  }
  return topics
    .map((topic) => (typeof topic === 'object' && topic && 'name' in topic ? String((topic as { name?: unknown }).name ?? '').trim() : ''))
    .filter((topic) => Boolean(topic))
    .slice(0, 4);
}

export function mapPostDetailToViewModel(dto: PostDetailDto): PostDetailViewModel {
  return {
    id: dto.id,
    text: dto.text ?? i18n.t('posts.mapper.textUnavailable'),
    date: formatDate(dto.date),
    commentsCount: new Intl.NumberFormat(i18n.language === 'ru' ? 'ru' : 'en').format(dto.comments_count),
    views: formatNullableNumber(dto.views),
    involvement: formatNullableRatio(dto.involvement),
  };
}

export function mapCommentToViewModel(dto: CommentDto): CommentViewModel {
  return {
    id: dto.id,
    tgMessageId: dto.tg_message_id,
    depth: dto.depth,
    date: formatDate(dto.date),
    text: dto.text,
    parentCommentId: dto.parent_comment_id,
    threadRootMessageId: dto.thread_root_tg_message_id,
    threadModeHint: dto.thread_root_tg_message_id !== null || dto.parent_comment_id !== null,
  };
}

export function mapReportToViewModel(dto: ReportDto | null): ReportViewModel | null {
  if (!dto) {
    return null;
  }

  return {
    id: dto.id,
    status: dto.status,
    content: dto.content ?? i18n.t('posts.report.emptyContent'),
    createdAt: formatDate(dto.created_at),
    summary: readReportSummary(dto.report_json),
    topics: readReportTopics(dto.report_json),
  };
}

export function mapLinkToViewModel(dto: LinkDto, currentPostId: number): LinkViewModel {
  const otherPostId = dto.src_post_id === currentPostId ? dto.dst_post_id : dto.src_post_id;

  return {
    id: dto.id,
    route: `/posts/${otherPostId}`,
    type: dto.link_type,
    direction: dto.direction,
    score: dto.score === null ? i18n.t('common.na') : dto.score.toFixed(2),
    status: dto.status,
    updatedAt: formatDate(dto.updated_at),
  };
}

export function mapPostDetailBundleToViewModel(bundle: PostDetailQueryBundle) {
  return {
    post: mapPostDetailToViewModel(bundle.post),
    comments: bundle.comments.map(mapCommentToViewModel),
    report: mapReportToViewModel(bundle.report),
    links: bundle.links.links.map((link) => mapLinkToViewModel(link, bundle.post.id)),
  };
}
