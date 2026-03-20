import { Link } from 'react-router-dom';

import { i18n } from '@shared/i18n/i18n';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
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
  return value === null ? i18n.t('common.na') : String(value);
}

export const keywordSearchColumns: DataTableColumn[] = [
  { id: 'select', label: i18n.t('keywordGraph.table.seed') },
  { id: 'post', label: i18n.t('keywordGraph.table.post') },
  { id: 'lemmas', label: i18n.t('keywordGraph.table.lemmas') },
  { id: 'metrics', label: i18n.t('keywordGraph.table.metrics') },
  { id: 'rank', label: i18n.t('keywordGraph.table.rank') },
];

export function mapKeywordSearchRows(
  items: KeywordSearchItemDto[],
  selectedPostIds: number[],
  excludedPostIds: number[],
  onToggleSelected: (postId: number) => void,
  onToggleExcluded: (postId: number) => void,
): DataTableRow[] {
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
                aria-label={i18n.t('keywordGraph.rows.selectPostAria', { id: item.post_id })}
              />{' '}
              {i18n.t('keywordGraph.actions.select')}
            </span>
            {isSelected ? (
              <span>
                <input
                  type="checkbox"
                  checked={isExcluded}
                  onChange={() => onToggleExcluded(item.post_id)}
                  aria-label={i18n.t('keywordGraph.rows.excludePostAria', { id: item.post_id })}
                />{' '}
                {i18n.t('keywordGraph.actions.exclude')}
              </span>
            ) : null}
          </label>
        ),
        post: (
          <div className="dashboard-table-shell__cell-stack">
            <strong>{i18n.t('keywordGraph.rows.postLabel', { id: item.post_id })}</strong>
            <span>@{item.channel_username ?? 'unknown_channel'}</span>
            <span>{formatUtcDateTime(item.date)}</span>
            <span>{item.text_preview ?? i18n.t('keywordGraph.rows.noPreview')}</span>
            <Link className="table-link" to={`/posts/${item.post_id}`}>
              {i18n.t('keywordGraph.rows.openPost')}
            </Link>
          </div>
        ),
        lemmas: item.matched_lemmas.length > 0 ? item.matched_lemmas.join(', ') : i18n.t('common.na'),
        metrics: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{i18n.t('keywordGraph.rows.comments', { value: item.comments_count })}</span>
            <span>{i18n.t('keywordGraph.rows.views', { value: formatNullableNumber(item.views) })}</span>
            <span>{i18n.t('keywordGraph.rows.involvement', { value: formatNullableNumber(item.involvement) })}</span>
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
    { id: 'total', label: i18n.t('keywordGraph.summary.matches'), value: String(response.total) },
    { id: 'lemmas', label: i18n.t('keywordGraph.summary.normalizedLemmas'), value: String(response.lemmas.length) },
    { id: 'latency', label: i18n.t('keywordGraph.summary.searchLatency'), value: `${response.took_ms} ms` },
    { id: 'normalized', label: i18n.t('keywordGraph.summary.normalizedQuery'), value: response.normalized_query },
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
    title: node.text_preview ?? i18n.t('keywordGraph.rows.noPreview'),
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
    score: edge.score === null ? i18n.t('common.na') : edge.score.toFixed(3),
    evidence: edge.evidence ? JSON.stringify(edge.evidence) : i18n.t('common.na'),
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

