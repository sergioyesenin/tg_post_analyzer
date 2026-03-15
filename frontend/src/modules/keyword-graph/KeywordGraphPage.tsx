import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

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

function toInlineMessage(error: unknown, fallback: string, t: (key: string, options?: Record<string, unknown>) => string) {
  if (error instanceof ApiError && error.status === 404) {
    return t('keywordGraph.messages.unavailable');
  }

  if (error instanceof ApiError && error.status === 403) {
    return t('keywordGraph.messages.forbiddenBackend');
  }

  return fallback;
}

export function KeywordGraphPage() {
  const { t } = useTranslation();
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
    ? toInlineMessage(searchQuery.error, t('keywordGraph.messages.searchFailedFallback'), t)
    : null;
  const buildErrorMessage = workspace.buildMutation.isError
    ? toInlineMessage(workspace.buildMutation.error, t('keywordGraph.messages.buildFailedFallback'), t)
    : null;
  const reportErrorMessage = workspace.reportMutation.isError
    ? toInlineMessage(workspace.reportMutation.error, t('keywordGraph.messages.reportFailedFallback'), t)
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
        meta: channel.category
          ? `${channel.category}${channel.is_active ? '' : ` • ${t('common.inactive')}`}`
          : channel.is_active
            ? t('common.active')
            : t('common.inactive'),
      })),
    [availableChannels, t],
  );

  if (searchQuery.isError && searchQuery.error instanceof ApiError && searchQuery.error.status === 403) {
    return (
      <ForbiddenState
        title={t('keywordGraph.forbiddenTitle')}
        description={t('keywordGraph.forbiddenDescription')}
      />
    );
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.advancedAnalysis')}</span>
          <h2>{t('navigation.keywordGraph')}</h2>
          <p>{t('keywordGraph.heroDescription')}</p>
        </div>
        <div className="dashboard-page__meta">
          <span>{t('keywordGraph.allowedRoles')}</span>
          <span>{t('keywordGraph.defaultGraphMode')}</span>
        </div>
      </section>

      <section className="dashboard-filter-bar" aria-label={t('keywordGraph.searchFormAria')}>
        <div className="dashboard-filter-bar__header">
          <div>
            <span className="state-card__eyebrow">{t('states.search')}</span>
            <strong>{t('keywordGraph.searchTitle')}</strong>
          </div>
          <code>{filters.query ? `query=${filters.query}` : t('keywordGraph.explicitSubmitOnly')}</code>
        </div>

        <div className="dashboard-filter-grid">
          <label>
            <span>{t('fields.query')}</span>
            <input
              aria-label={t('keywordGraph.queryAria')}
              value={formState.query}
              onChange={(event) => setFormState((current) => ({ ...current, query: event.target.value }))}
              placeholder="policy shift"
            />
          </label>
          <label>
            <span>{t('fields.limit')}</span>
            <input
              aria-label={t('fields.searchLimit')}
              type="number"
              min={1}
              max={200}
              value={formState.limit}
              onChange={(event) => setFormState((current) => ({ ...current, limit: event.target.value }))}
            />
          </label>
          <label>
            <span>{t('fields.dateFrom')}</span>
            <input
              type="date"
              value={formState.date_from}
              onChange={(event) => setFormState((current) => ({ ...current, date_from: event.target.value }))}
            />
          </label>
          <label>
            <span>{t('fields.dateTo')}</span>
            <input
              type="date"
              value={formState.date_to}
              onChange={(event) => setFormState((current) => ({ ...current, date_to: event.target.value }))}
            />
          </label>
          <fieldset className="detail-block">
            <legend>{t('fields.channels')}</legend>
            {channelsQuery.isLoading ? (
              <p className="dashboard-panel-copy">{t('keywordGraph.channels.loading')}</p>
            ) : channelsQuery.isError ? (
              <p className="dashboard-panel-copy">{t('keywordGraph.channels.error')}</p>
            ) : channelOptions.length === 0 ? (
              <p className="dashboard-panel-copy">{t('keywordGraph.channels.empty')}</p>
            ) : (
              <div className="detail-list" aria-label={t('keywordGraph.channels.optionsAria')}>
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
                          aria-label={t('keywordGraph.channels.channelAria', { label: channel.label })}
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
            {t('actions.resetSearch')}
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
            {t('actions.searchPosts')}
          </button>
        </div>
      </section>

      {searchSummaryCards.length > 0 ? <DashboardSummaryCards cards={searchSummaryCards} /> : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          {filters.query.trim().length < 2 ? (
            <EmptyState
              title={t('keywordGraph.startTitle')}
              description={t('keywordGraph.startDescription')}
            />
          ) : searchQuery.isLoading ? (
            <LoadingState title={t('keywordGraph.loadingTitle')} description={t('keywordGraph.loadingDescription')} />
          ) : searchErrorMessage ? (
            <ErrorState title={t('keywordGraph.searchFailedTitle')} description={searchErrorMessage} />
          ) : searchRows.length === 0 ? (
            <EmptyState title={t('keywordGraph.noResultsTitle')} description={t('keywordGraph.noResultsDescription')} />
          ) : (
            <DashboardTableShell
              title={t('keywordGraph.resultsTitle')}
              description={resultMeta.tookMs ? t('keywordGraph.resultsDescriptionWithTiming', { tookMs: resultMeta.tookMs }) : t('keywordGraph.resultsDescription')}
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
                <span className="state-card__eyebrow">{t('states.seedSet')}</span>
                <strong>{t('keywordGraph.selectedPostsTitle')}</strong>
              </div>
            </div>

            {workspace.selectedItems.length === 0 ? (
              <p className="dashboard-panel-copy">{t('keywordGraph.selectedPostsEmpty')}</p>
            ) : (
              <div className="detail-list">
                {workspace.selectedItems.map((item) => (
                  <div key={item.post_id} className="detail-list__item">
                    <div>
                      <strong>{t('keywordGraph.rows.postLabel', { id: item.post_id })}</strong>
                      <p>{item.text_preview ?? t('keywordGraph.rows.noPreview')}</p>
                    </div>
                    <div className="detail-list__actions">
                      <span>@{item.channel_username ?? 'unknown_channel'}</span>
                      <span>{workspace.excludedPostIds.includes(item.post_id) ? t('common.excluded') : t('common.included')}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">{t('states.build')}</span>
                <strong>{t('keywordGraph.buildTitle')}</strong>
              </div>
            </div>

            <div className="dashboard-filter-grid">
              <label>
                <span>{t('fields.graphMode')}</span>
                <select
                  value={workspace.graphConfig.graph_mode}
                  onChange={(event) =>
                    workspace.setGraphConfig((current) => ({
                      ...current,
                      graph_mode: event.target.value as 'transient' | 'persisted',
                    }))
                  }
                >
                  <option value="transient">{t('common.transient')}</option>
                  <option value="persisted">{t('common.persisted')}</option>
                </select>
              </label>
              <label>
                <span>{t('fields.neighborDepth')}</span>
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
                  {t('fields.includeNeighbors')}
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
                {t('actions.buildGraph')}
              </button>
            </div>
          </section>

          {canGenerateReport ? (
            <section className="detail-block">
              <div className="detail-block__header">
                <div>
                  <span className="state-card__eyebrow">{t('states.report')}</span>
                  <strong>{t('keywordGraph.reportTitle')}</strong>
                </div>
              </div>

              <label className="dashboard-filter-grid">
                <span>{t('fields.reportTitle')}</span>
                <input
                  aria-label={t('keywordGraph.reportTitleAria')}
                  value={reportTitle}
                  onChange={(event) => setReportTitle(event.target.value)}
                  placeholder={t('keywordGraph.reportPlaceholder')}
                />
              </label>

              <div className="dashboard-filter-bar__actions">
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={workspace.selectedPostIds.length === 0 || workspace.reportMutation.isPending}
                  onClick={() => workspace.reportMutation.mutate(reportTitle.trim())}
                >
                  {t('actions.generateReport')}
                </button>
              </div>

              {workspace.reportMutation.isPending ? (
                <LoadingState title={t('keywordGraph.reportLoadingTitle')} description={t('keywordGraph.reportLoadingDescription')} />
              ) : null}

              {reportErrorMessage ? <ErrorState title={t('keywordGraph.reportErrorTitle')} description={reportErrorMessage} /> : null}

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

