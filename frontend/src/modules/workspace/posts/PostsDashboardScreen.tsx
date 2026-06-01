import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
import {
  getDashboardEmptyFeedback,
  getDashboardErrorFilterFeedback,
  type DashboardFilterFeedback,
} from '@shared/dashboard/filter-feedback';
import { getPostsDashboardFilterOptions, type DashboardFilterOptionsByMode } from '@shared/dashboard/filter-options';
import type { PostsDashboardFiltersDto } from '@shared/dashboard/contracts';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import {
  getDashboardSearchAvailabilityFeedback,
  getDashboardSearchDisabledReason,
  isDashboardSearchAllowedForRole,
} from '@shared/dashboard/search-availability';
import { QueryActivityNotice, ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { useSession } from '@app/providers/SessionProvider';
import { useChannelsQuery } from '@modules/admin/hooks';
import { usePostsDashboardQuery, usePostsKeywordSearchQuery } from '@modules/workspace/posts/hooks';
import {
  mapPostsDashboardToViewModel,
  mapPostsRowsToTableRows,
  postsDashboardColumns,
} from '@modules/workspace/posts/mappers';

function PostsDashboardScaffold({
  children,
  filters,
  filterOptions,
  channelOptionsState,
  applyFilters,
  resetFilters,
  applySearch,
  resetSearch,
  searchDisabled,
  searchDisabledReason,
  searchFeedback = null,
  feedback = null,
}: {
  children: ReactNode;
  filters: PostsDashboardFiltersDto;
  filterOptions: DashboardFilterOptionsByMode['posts'];
  channelOptionsState: 'ready' | 'loading' | 'error';
  applyFilters: (filters: PostsDashboardFiltersDto) => void;
  resetFilters: () => void;
  applySearch: (query: string) => void;
  resetSearch: () => void;
  searchDisabled: boolean;
  searchDisabledReason: string | null;
  searchFeedback?: DashboardFilterFeedback | null;
  feedback?: DashboardFilterFeedback | null;
}) {
  const { t } = useTranslation();

  return (
    <div className="dashboard-page dashboard-page--analytics">
      <section className="dashboard-page__hero dashboard-page__hero--analytics">
        <div>
          <h2>{t('posts.dashboard.heroTitle')}</h2>
          <p>{t('posts.dashboard.sourceDescription')}</p>
        </div>
      </section>

      <DashboardFilterBar
        mode="posts"
        filters={filters}
        options={filterOptions}
        channelOptionsState={channelOptionsState}
        feedback={feedback}
        headerSlot={null}
        onApply={applyFilters}
        onReset={resetFilters}
        onApplySearch={applySearch}
        onResetSearch={resetSearch}
        searchDisabled={searchDisabled}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={searchFeedback}
      />
      {children}
    </div>
  );
}

export function PostsDashboardScreen() {
  const { t } = useTranslation();
  const { filters, applyFilters, resetFilters, applySearch, resetSearch } = useDashboardFilters('posts');
  const { primaryRole } = useSession();
  const isSearchAllowed = isDashboardSearchAllowedForRole(primaryRole);
  const searchDisabledReason = getDashboardSearchDisabledReason(primaryRole, t);
  const query = usePostsDashboardQuery(filters);
  const keywordSearchQuery = usePostsKeywordSearchQuery(filters, { enabled: isSearchAllowed });
  const keywordSearchAvailabilityFeedback = getDashboardSearchAvailabilityFeedback(keywordSearchQuery.error, t);
  const channelsQuery = useChannelsQuery();
  const data = query.data ?? null;
  const filterOptions = getPostsDashboardFilterOptions({
    filters,
    dashboardData: data,
    channels: channelsQuery.data,
  });
  const channelOptionsState = channelsQuery.isLoading ? 'loading' : channelsQuery.isError ? 'error' : 'ready';

  if (query.isLoading && !data) {
    return (
      <PostsDashboardScaffold
        filters={filters}
        filterOptions={filterOptions}
        channelOptionsState={channelOptionsState}
        applyFilters={applyFilters}
        resetFilters={resetFilters}
        applySearch={applySearch}
        resetSearch={resetSearch}
        searchDisabled={!isSearchAllowed}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={keywordSearchAvailabilityFeedback}
      >
        <LoadingState title={t('posts.dashboard.loadingTitle')} description={t('posts.dashboard.loadingDescription')} />
      </PostsDashboardScaffold>
    );
  }

  if (query.isError && !data) {
    const error = query.error;
    const isForbidden = error instanceof ApiError && error.status === 403;

    return (
      <PostsDashboardScaffold
        filters={filters}
        filterOptions={filterOptions}
        channelOptionsState={channelOptionsState}
        applyFilters={applyFilters}
        resetFilters={resetFilters}
        applySearch={applySearch}
        resetSearch={resetSearch}
        searchDisabled={!isSearchAllowed}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={keywordSearchAvailabilityFeedback}
        feedback={getDashboardErrorFilterFeedback(t)}
      >
        {isForbidden ? (
          <ForbiddenState title={t('posts.dashboard.forbiddenTitle')} description={t('posts.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('posts.dashboard.errorTitle')} description={t('posts.dashboard.errorDescription')} />
        )}
      </PostsDashboardScaffold>
    );
  }

  if (!data) {
    return (
      <PostsDashboardScaffold
        filters={filters}
        filterOptions={filterOptions}
        channelOptionsState={channelOptionsState}
        applyFilters={applyFilters}
        resetFilters={resetFilters}
        applySearch={applySearch}
        resetSearch={resetSearch}
        searchDisabled={!isSearchAllowed}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={keywordSearchAvailabilityFeedback}
        feedback={getDashboardErrorFilterFeedback(t)}
      >
        <ErrorState title={t('posts.dashboard.noDataTitle')} description={t('posts.dashboard.noDataDescription')} />
      </PostsDashboardScaffold>
    );
  }

  const viewModel = mapPostsDashboardToViewModel(data, primaryRole);
  const emptyUiState = getDashboardEmptyFeedback('posts', filters, t);
  const isKeywordSearchActive = filters.query.trim().length >= 2;
  const matchedPostIds = keywordSearchQuery.data
    ? new Set(keywordSearchQuery.data.items.map((item) => item.post_id))
    : null;
  const filteredRows = matchedPostIds
    ? viewModel.rows.filter((row) => matchedPostIds.has(row.postId))
    : viewModel.rows;
  const hasKeywordFilteredRows = isKeywordSearchActive && keywordSearchQuery.isSuccess && matchedPostIds !== null;
  const isKeywordSearchEmptyWithinSnapshot = hasKeywordFilteredRows && keywordSearchQuery.data.items.length > 0 && filteredRows.length === 0;
  const rows = hasKeywordFilteredRows ? filteredRows : viewModel.rows;
  const keywordSearchEmptyState = {
    filterBar: {
      tone: 'warning' as const,
      title: t('posts.dashboard.keywordSearch.emptyFeedbackTitle', {
        defaultValue: 'По этому запросу постов в текущей выборке нет',
      }),
      description: t('posts.dashboard.keywordSearch.emptyFeedbackDescription', {
        defaultValue: 'Поиск нашел материалы по запросу, но они не попали в текущую выборку. Уточните запрос или расширьте фильтры.',
      }),
    },
    stateCard: {
      title: t('posts.dashboard.keywordSearch.emptyStateTitle', {
        defaultValue: 'По этому запросу постов в текущей выборке нет',
      }),
      description: t('posts.dashboard.keywordSearch.emptyStateDescription', {
        defaultValue: 'Совпадения по запросу есть, но в текущей выборке они не отображаются. Попробуйте другой запрос или более широкий диапазон фильтров.',
      }),
    },
  };
  const emptyFeedback = isKeywordSearchEmptyWithinSnapshot ? keywordSearchEmptyState : emptyUiState;
  const filterFeedback = rows.length === 0 ? emptyFeedback.filterBar : null;

  return (
    <div className="dashboard-page dashboard-page--analytics">
      <DashboardSystemAlerts warnings={viewModel.warnings} partial={viewModel.isPartial} />

      <section className="dashboard-page__hero dashboard-page__hero--analytics">
        <div>
          <h2>{t('posts.dashboard.heroTitle')}</h2>
          <p>{t('posts.dashboard.heroDescription')}</p>
        </div>
      </section>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      <DashboardFilterBar
        mode="posts"
        filters={filters}
        options={filterOptions}
        channelOptionsState={channelOptionsState}
        feedback={filterFeedback}
        headerSlot={<DashboardGeneratedAt generatedAt={viewModel.generatedAt} />}
        onApply={applyFilters}
        onReset={resetFilters}
        onApplySearch={applySearch}
        onResetSearch={resetSearch}
        searchDisabled={!isSearchAllowed}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={keywordSearchAvailabilityFeedback}
      />

      {query.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('posts.dashboard.refreshingTitle', { defaultValue: 'Данные обновляются' })}
          description={t('posts.dashboard.refreshingDescription', { defaultValue: 'Текущий список остается на экране, пока загружаются обновленные данные.' })}
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('posts.dashboard.keywordSearch.loadingTitle', { defaultValue: 'Ищем посты по запросу' })}
          description={t('posts.dashboard.keywordSearch.loadingDescription', { defaultValue: 'Текущая таблица остается на экране, пока обновляются результаты поиска.' })}
        />
      ) : null}

      {query.isError ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('posts.dashboard.refreshErrorTitle', { defaultValue: 'Не удалось обновить данные' })}
          description={t('posts.dashboard.refreshErrorDescription', { defaultValue: 'Показываем последнюю доступную версию списка, чтобы вы могли продолжить работу.' })}
          tone="danger"
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isError && !keywordSearchAvailabilityFeedback ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('posts.dashboard.keywordSearch.errorTitle', { defaultValue: 'Не удалось применить поиск' })}
          description={t('posts.dashboard.keywordSearch.errorDescription', { defaultValue: 'Показываем текущую выборку без изменений. Повторите попытку или скорректируйте запрос.' })}
          tone="danger"
        />
      ) : null}

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('posts.dashboard.readOnlyTitle')} description={t('posts.dashboard.readOnlyDescription')} />
      ) : null}

      {rows.length === 0 ? (
        <EmptyState title={emptyFeedback.stateCard.title} description={emptyFeedback.stateCard.description} />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--single">
          <div className="dashboard-page__primary">
            <AnalyticsTable
              title={t('posts.dashboard.tableTitle')}
              description={t('posts.dashboard.tableDescription')}
              columns={postsDashboardColumns}
              rows={mapPostsRowsToTableRows(rows)}
            />
          </div>
        </section>
      )}
    </div>
  );
}
