import type {
  CommentDto,
  LinkDto,
  PostDetailDto,
  PostDetailQueryBundle,
  ReportDto,
} from '@modules/workspace/post-detail/contracts';

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
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatNullableNumber(value: number | null) {
  return value === null ? '—' : new Intl.NumberFormat('en').format(value);
}

function formatNullableRatio(value: number | null) {
  return value === null ? '—' : value.toFixed(2);
}

export function mapPostDetailToViewModel(dto: PostDetailDto): PostDetailViewModel {
  return {
    id: dto.id,
    text: dto.text ?? 'Post text is unavailable.',
    date: formatDate(dto.date),
    commentsCount: new Intl.NumberFormat('en').format(dto.comments_count),
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
    content: dto.content ?? 'Report content is empty.',
    createdAt: formatDate(dto.created_at),
  };
}

export function mapLinkToViewModel(dto: LinkDto, currentPostId: number): LinkViewModel {
  const otherPostId = dto.src_post_id === currentPostId ? dto.dst_post_id : dto.src_post_id;

  return {
    id: dto.id,
    route: `/posts/${otherPostId}`,
    type: dto.link_type,
    direction: dto.direction,
    score: dto.score === null ? '—' : dto.score.toFixed(2),
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
