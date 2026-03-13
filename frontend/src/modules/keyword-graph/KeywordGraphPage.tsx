import { useEffect, useMemo, useState } from 'react';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { canPerformAction } from '@shared/routing/policy';
import { KeywordGraphPanel } from '@modules/keyword-graph/components/KeywordGraphPanel';
import { useKeywordChannelsQuery, useKeywordGraphWorkspace, useKeywordSearchFilters, useKeywordSearchQuery } from '@modules/keyword-graph/hooks';
import { keywordSearchColumns, mapKeywordGraphToPanel, mapKeywordSearchRows, mapKeywordSearchSummary } from '@modules/keyword-graph/mappers';

function toInlineMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.status === 404) {
    return 'Keyword graph is unavailable for this account or environment. Backend feature flag or rollout gate denied the request.';
  }

  if (error instanceof ApiError && error.status === 403) {
    return 'Keyword graph access is forbidden by backend RBAC.';
  }

  return fallback;
}

export function KeywordGraphPage() {
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const canGenerateReport = canPerformAction('reports.generate', roles);
  const { filters, applyFilters, resetFilters } = useKeywordSearchFilters();
  const channelsQuery = useKeywordChannelsQuery();
  const [formState, setFormState] = useState({
    query: filters.query,
    limit: String(filters.limit),
    date_from: filters.date_from,
    date_to: filters.date_to,
    channel_ids: filters.channel_ids,
  });
  const searchQuery = useKeywordSearchQuery(filters);
  const searchItems = useMemo(() => searchQuery.data?.items ?? [], [searchQuery.data?.items]);
  const searchSummaryCards = mapKeywordSearchSummary(searchQuery.data ?? null);
  const workspace = useKeywordGraphWorkspace(searchItems);
  const [reportTitle, setReportTitle] = useState('');

  useEffect(() => {
    setFormState({
      query: filters.query,
      limit: String(filters.limit),
      date_from: filters.date_from,
      date_to: filters.date_to,
      channel_ids: filters.channel_ids,
    });
  }, [filters]);

  const graphPanel = mapKeywordGraphToPanel(workspace.graphResult);
  const searchRows = mapKeywordSearchRows(
    searchItems,
    workspace.selectedPostIds,
    workspace.excludedPostIds,
    workspace.toggleSelected,
    workspace.toggleExcluded,
  );
  const searchErrorMessage = searchQuery.isError
    ? toInlineMessage(searchQuery.error, 'The keyword search request failed.')
    : null;
  const buildErrorMessage = workspace.buildMutation.isError
    ? toInlineMessage(workspace.buildMutation.error, 'The keyword graph build request failed.')
    : null;
  const reportErrorMessage = workspace.reportMutation.isError
    ? toInlineMessage(workspace.reportMutation.error, 'The keyword graph report request failed.')
    : null;
  const reportStatus = workspace.reportMutation.data?.status ?? null;
  const reportContent = workspace.reportMutation.data?.content ?? null;
  const resultMeta = useMemo(
    () => ({
      normalizedQuery: searchQuery.data?.normalized_query ?? null,
      lemmas: searchQuery.data?.lemmas ?? [],
      tookMs: searchQuery.data?.took_ms ?? null,
    }),
    [searchQuery.data],
  );
  const availableChannels = channelsQuery.data ?? [];
  const channelOptions = useMemo(
    () =>
      availableChannels.map((channel) => ({
        id: channel.id,
        label: channel.title ? `${channel.title} (@${channel.username})` : `@${channel.username}`,
        meta: channel.category ? `${channel.category}${channel.is_active ? '' : ' · inactive'}` : channel.is_active ? 'active' : 'inactive',
      })),
    [availableChannels],
  );

  if (searchQuery.isError && searchQuery.error instanceof ApiError && searchQuery.error.status === 403) {
    return (
      <ForbiddenState
        title="Keyword graph is restricted"
        description="The route is visible, but the backend denied access to the keyword graph tool."
      />
    );
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">advanced analysis</span>
          <h2>Keyword graph</h2>
          <p>
            Separate analytical tool for keyword-driven post search, graph build, and optional report generation. It is not part of
            the main dashboard modes.
          </p>
        </div>
        <div className="dashboard-page__meta">
          <span>Allowed roles: admin, analyst</span>
          <span>Graph mode defaults to transient</span>
        </div>
      </section>

      <section className="dashboard-filter-bar" aria-label="Keyword graph search form">
        <div className="dashboard-filter-bar__header">
          <div>
            <span className="state-card__eyebrow">search</span>
            <strong>Search posts by keyword or phrase</strong>
          </div>
          <code>{filters.query ? `query=${filters.query}` : 'explicit submit only'}</code>
        </div>

        <div className="dashboard-filter-grid">
          <label>
            <span>Query</span>
            <input
              aria-label="Keyword query"
              value={formState.query}
              onChange={(event) => setFormState((current) => ({ ...current, query: event.target.value }))}
              placeholder="policy shift"
            />
          </label>
          <label>
            <span>Limit</span>
            <input
              aria-label="Search limit"
              type="number"
              min={1}
              max={200}
              value={formState.limit}
              onChange={(event) => setFormState((current) => ({ ...current, limit: event.target.value }))}
            />
          </label>
          <label>
            <span>Date from</span>
            <input
              type="date"
              value={formState.date_from}
              onChange={(event) => setFormState((current) => ({ ...current, date_from: event.target.value }))}
            />
          </label>
          <label>
            <span>Date to</span>
            <input
              type="date"
              value={formState.date_to}
              onChange={(event) => setFormState((current) => ({ ...current, date_to: event.target.value }))}
            />
          </label>
          <fieldset className="detail-block">
            <legend>Channels</legend>
            {channelsQuery.isLoading ? (
              <p className="dashboard-panel-copy">Loading channel options from the backend.</p>
            ) : channelsQuery.isError ? (
              <p className="dashboard-panel-copy">
                Channel list is unavailable, so channel-scoped filtering cannot be applied right now.
              </p>
            ) : channelOptions.length === 0 ? (
              <p className="dashboard-panel-copy">No channels are available for filtering.</p>
            ) : (
              <div className="detail-list" aria-label="Channel filter options">
                {channelOptions.map((channel) => {
                  const isChecked = formState.channel_ids.includes(channel.id);

                  return (
                    <label key={channel.id} className="detail-list__item">
                      <span>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() =>
                            setFormState((current) => ({
                              ...current,
                              channel_ids: isChecked
                                ? current.channel_ids.filter((value) => value !== channel.id)
                                : [...current.channel_ids, channel.id],
                            }))
                          }
                          aria-label={`Channel ${channel.label}`}
                        />{' '}
                        {channel.label}
                      </span>
                      <span>{channel.meta}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </fieldset>
        </div>

        <div className="dashboard-filter-bar__actions">
          <button type="button" className="dashboard-button dashboard-button--ghost" onClick={resetFilters}>
            Reset search
          </button>
          <button
            type="button"
            className="dashboard-button"
            onClick={() =>
              applyFilters({
                query: formState.query.trim(),
                limit: Number(formState.limit) || 50,
                date_from: formState.date_from,
                date_to: formState.date_to,
                channel_ids: formState.channel_ids,
              })
            }
          >
            Search posts
          </button>
        </div>
      </section>

      {searchSummaryCards.length > 0 ? <DashboardSummaryCards cards={searchSummaryCards} /> : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {filters.query.trim().length < 2 ? (
            <EmptyState
              title="Start with a keyword search"
              description="Enter a query of at least two characters and submit the form to build an analytical seed set."
            />
          ) : searchQuery.isLoading ? (
            <LoadingState title="Searching posts" description="Looking up posts through POST /api/keyword/search/posts." />
          ) : searchErrorMessage ? (
            <ErrorState title="Keyword search failed" description={searchErrorMessage} />
          ) : searchRows.length === 0 ? (
            <EmptyState title="No posts matched the query" description="The search request succeeded, but no posts matched the current keyword and filter set." />
          ) : (
            <DashboardTableShell
              title="Search results"
              description={`Matched posts for the analytical query.${resultMeta.tookMs ? ` Took ${resultMeta.tookMs} ms.` : ''}`}
              columns={keywordSearchColumns}
              rows={searchRows}
            />
          )}

          <KeywordGraphPanel
            viewModel={graphPanel}
            isLoading={workspace.buildMutation.isPending}
            errorMessage={buildErrorMessage}
            onRefresh={() => {
              if (workspace.selectedPostIds.length === 0) {
                return;
              }
              workspace.buildMutation.mutate();
            }}
          />
        </div>

        <div className="dashboard-page__secondary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">seed set</span>
                <strong>Selected posts</strong>
              </div>
            </div>

            {workspace.selectedItems.length === 0 ? (
              <p className="dashboard-panel-copy">Select posts from the search results table to define the graph seed set.</p>
            ) : (
              <div className="detail-list">
                {workspace.selectedItems.map((item) => (
                  <div key={item.post_id} className="detail-list__item">
                    <div>
                      <strong>Post #{item.post_id}</strong>
                      <p>{item.text_preview ?? 'No preview available.'}</p>
                    </div>
                    <div className="detail-list__actions">
                      <span>@{item.channel_username ?? 'unknown_channel'}</span>
                      <span>{workspace.excludedPostIds.includes(item.post_id) ? 'Excluded' : 'Included'}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">build</span>
                <strong>Graph build flow</strong>
              </div>
            </div>

            <div className="dashboard-filter-grid">
              <label>
                <span>Graph mode</span>
                <select
                  value={workspace.graphConfig.graph_mode}
                  onChange={(event) =>
                    workspace.setGraphConfig((current) => ({
                      ...current,
                      graph_mode: event.target.value as 'transient' | 'persisted',
                    }))
                  }
                >
                  <option value="transient">transient</option>
                  <option value="persisted">persisted</option>
                </select>
              </label>
              <label>
                <span>Neighbor depth</span>
                <input
                  type="number"
                  min={0}
                  max={3}
                  value={workspace.graphConfig.neighbor_depth}
                  onChange={(event) =>
                    workspace.setGraphConfig((current) => ({
                      ...current,
                      neighbor_depth: Math.max(0, Math.min(3, Number(event.target.value) || 0)),
                    }))
                  }
                />
              </label>
              <label>
                <span>
                  <input
                    type="checkbox"
                    checked={workspace.graphConfig.include_neighbors}
                    onChange={(event) =>
                      workspace.setGraphConfig((current) => ({
                        ...current,
                        include_neighbors: event.target.checked,
                      }))
                    }
                  />{' '}
                  Include neighbors
                </span>
              </label>
            </div>

            <div className="dashboard-filter-bar__actions">
              <button
                type="button"
                className="dashboard-button"
                disabled={workspace.selectedPostIds.length === 0 || workspace.buildMutation.isPending}
                onClick={() => workspace.buildMutation.mutate()}
              >
                Build graph
              </button>
            </div>
          </section>

          {canGenerateReport ? (
            <section className="detail-block">
              <div className="detail-block__header">
                <div>
                  <span className="state-card__eyebrow">report</span>
                  <strong>Graph report</strong>
                </div>
              </div>

              <label className="dashboard-filter-grid">
                <span>Report title</span>
                <input
                  aria-label="Graph report title"
                  value={reportTitle}
                  onChange={(event) => setReportTitle(event.target.value)}
                  placeholder="Keyword graph report"
                />
              </label>

              <div className="dashboard-filter-bar__actions">
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={workspace.selectedPostIds.length === 0 || workspace.reportMutation.isPending}
                  onClick={() => workspace.reportMutation.mutate(reportTitle.trim())}
                >
                  Generate report
                </button>
              </div>

              {workspace.reportMutation.isPending ? (
                <LoadingState title="Generating keyword graph report" description="Calling POST /api/keyword/graph/report for the current seed set." />
              ) : null}

              {reportErrorMessage ? <ErrorState title="Keyword graph report failed" description={reportErrorMessage} /> : null}

              {reportContent ? (
                <div className="report-block">
                  <div className="report-block__meta">
                    <strong>{workspace.reportMutation.data?.title}</strong>
                    <span>{reportStatus}</span>
                  </div>
                  <pre className="report-block__content">{reportContent}</pre>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}
