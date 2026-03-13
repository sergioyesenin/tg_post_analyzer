import { Link } from 'react-router-dom';

import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import { formatNullableRatio, formatUtcDateTime } from '@shared/utils/formatters';
import type {
  KeywordGraphBuildResponseDto,
  KeywordGraphEdgeDto,
  KeywordGraphNodeDto,
  KeywordSearchItemDto,
  KeywordSearchResponseDto,
} from '@modules/keyword-graph/contracts';

function formatNullableNumber(value: number | null) {
  return value === null ? 'n/a' : String(value);
}

export const keywordSearchColumns: DashboardTableColumn[] = [
  { id: 'select', label: 'Seed' },
  { id: 'post', label: 'Post' },
  { id: 'lemmas', label: 'Matched lemmas' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'rank', label: 'Rank' },
];

export function mapKeywordSearchRows(
  items: KeywordSearchItemDto[],
  selectedPostIds: number[],
  excludedPostIds: number[],
  onToggleSelected: (postId: number) => void,
  onToggleExcluded: (postId: number) => void,
): DashboardTableRow[] {
  return items.map((item) => {
    const isSelected = selectedPostIds.includes(item.post_id);
    const isExcluded = excludedPostIds.includes(item.post_id);

    return {
      id: String(item.post_id),
      isSelected,
      cells: {
        select: (
          <label className="dashboard-table-shell__cell-stack">
            <span>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleSelected(item.post_id)}
                aria-label={`Select post ${item.post_id}`}
              />{' '}
              Select
            </span>
            {isSelected ? (
              <span>
                <input
                  type="checkbox"
                  checked={isExcluded}
                  onChange={() => onToggleExcluded(item.post_id)}
                  aria-label={`Exclude post ${item.post_id}`}
                />{' '}
                Exclude
              </span>
            ) : null}
          </label>
        ),
        post: (
          <div className="dashboard-table-shell__cell-stack">
            <strong>Post #{item.post_id}</strong>
            <span>@{item.channel_username ?? 'unknown_channel'}</span>
            <span>{formatUtcDateTime(item.date)}</span>
            <span>{item.text_preview ?? 'No preview available.'}</span>
            <Link className="table-link" to={`/posts/${item.post_id}`}>
              Open post
            </Link>
          </div>
        ),
        lemmas: item.matched_lemmas.length > 0 ? item.matched_lemmas.join(', ') : 'n/a',
        metrics: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{item.comments_count} comments</span>
            <span>{formatNullableNumber(item.views)} views</span>
            <span>{formatNullableNumber(item.involvement)} involvement</span>
          </div>
        ),
        rank: item.rank.toFixed(3),
      },
    };
  });
}

export function mapKeywordSearchSummary(response: KeywordSearchResponseDto | null): DashboardSummaryCard[] {
  if (!response) {
    return [];
  }

  return [
    { id: 'total', label: 'Matches', value: String(response.total) },
    { id: 'lemmas', label: 'Normalized lemmas', value: String(response.lemmas.length) },
    { id: 'latency', label: 'Search latency', value: `${response.took_ms} ms` },
    { id: 'normalized', label: 'Normalized query', value: response.normalized_query },
  ];
}

type KeywordGraphNodeViewModel = {
  id: string;
  postId: number;
  title: string;
  date: string;
  channel: string;
  commentsCount: number;
  views: string;
  involvement: string;
  includedBy: string;
};

type KeywordGraphEdgeViewModel = {
  id: string;
  sourcePostId: number;
  targetPostId: number;
  label: string;
  status: string;
  source: string;
  score: string;
  evidence: string;
};

export type KeywordGraphPanelViewModel = {
  seedCount: number;
  excludedCount: number;
  nodeCount: number;
  edgeCount: number;
  tookMs: number;
  metaEntries: Array<{ key: string; value: string }>;
  nodes: KeywordGraphNodeViewModel[];
  edges: KeywordGraphEdgeViewModel[];
};

function mapNode(node: KeywordGraphNodeDto): KeywordGraphNodeViewModel {
  return {
    id: String(node.post_id),
    postId: node.post_id,
    title: node.text_preview ?? 'No preview available.',
    date: formatUtcDateTime(node.date),
    channel: `@${node.channel_username ?? 'unknown_channel'}`,
    commentsCount: node.comments_count,
    views: formatNullableNumber(node.views),
    involvement: formatNullableRatio(node.involvement),
    includedBy: node.included_by,
  };
}

function mapEdge(edge: KeywordGraphEdgeDto): KeywordGraphEdgeViewModel {
  return {
    id: String(edge.link_id),
    sourcePostId: edge.src_post_id,
    targetPostId: edge.dst_post_id,
    label: edge.link_type,
    status: edge.status,
    source: edge.edge_source,
    score: edge.score === null ? 'n/a' : edge.score.toFixed(3),
    evidence: edge.evidence ? JSON.stringify(edge.evidence) : 'n/a',
  };
}

export function mapKeywordGraphToPanel(result: KeywordGraphBuildResponseDto | null): KeywordGraphPanelViewModel | null {
  if (!result) {
    return null;
  }

  return {
    seedCount: result.seed_post_ids.length,
    excludedCount: result.excluded_post_ids.length,
    nodeCount: result.nodes.length,
    edgeCount: result.edges.length,
    tookMs: result.took_ms,
    metaEntries: Object.entries(result.meta).map(([key, value]) => ({
      key,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    })),
    nodes: result.nodes.map(mapNode),
    edges: result.edges.map(mapEdge),
  };
}
