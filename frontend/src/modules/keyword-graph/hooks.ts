import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';

import { getChannels } from '@modules/admin/api';
import { buildKeywordGraph, generateKeywordGraphReport, searchPostsByKeyword } from '@modules/keyword-graph/api';
import type {
  KeywordGraphBuildResponseDto,
  KeywordGraphConfig,
  KeywordSearchFilters,
  KeywordSearchItemDto,
} from '@modules/keyword-graph/contracts';
import { parseKeywordSearchFilters, serializeKeywordSearchFilters } from '@modules/keyword-graph/filters';
import { keywordGraphQueryKeys } from '@modules/keyword-graph/query-keys';

export function useKeywordSearchFilters() {
  const location = useLocation();
  const navigate = useNavigate();
  const filters = useMemo(() => parseKeywordSearchFilters(location.search), [location.search]);

  const applyFilters = (nextFilters: KeywordSearchFilters) => {
    const query = serializeKeywordSearchFilters(nextFilters);
    navigate(
      {
        pathname: location.pathname,
        search: query ? `?${query}` : '',
      },
      { replace: false },
    );
  };

  const resetFilters = () => {
    navigate(
      {
        pathname: location.pathname,
        search: '',
      },
      { replace: false },
    );
  };

  return {
    filters,
    applyFilters,
    resetFilters,
  };
}

export function useKeywordChannelsQuery() {
  return useQuery({
    queryKey: keywordGraphQueryKeys.channels(),
    queryFn: getChannels,
    retry: false,
  });
}

export function useKeywordSearchQuery(filters: KeywordSearchFilters) {
  const queryKey = serializeKeywordSearchFilters(filters);
  const isEnabled = filters.query.trim().length >= 2;

  return useQuery({
    queryKey: keywordGraphQueryKeys.search(queryKey),
    queryFn: () => searchPostsByKeyword(filters),
    enabled: isEnabled,
    retry: false,
  });
}

export function useKeywordGraphWorkspace(searchItems: KeywordSearchItemDto[]) {
  const [selectedPostIds, setSelectedPostIds] = useState<number[]>([]);
  const [excludedPostIds, setExcludedPostIds] = useState<number[]>([]);
  const [graphConfig, setGraphConfig] = useState<KeywordGraphConfig>({
    graph_mode: 'transient',
    include_neighbors: true,
    neighbor_depth: 1,
  });
  const [graphResult, setGraphResult] = useState<KeywordGraphBuildResponseDto | null>(null);

  useEffect(() => {
    setSelectedPostIds([]);
    setExcludedPostIds([]);
    setGraphResult(null);
  }, [searchItems]);

  const selectedItems = useMemo(
    () => searchItems.filter((item) => selectedPostIds.includes(item.post_id)),
    [searchItems, selectedPostIds],
  );
  const selectedKey = selectedPostIds.join(',');
  const excludedKey = excludedPostIds.join(',');

  const buildMutation = useMutation({
    mutationFn: () =>
      buildKeywordGraph({
        post_ids: selectedPostIds,
        exclude_post_ids: excludedPostIds,
        graph_mode: graphConfig.graph_mode,
        include_neighbors: graphConfig.include_neighbors,
        neighbor_depth: graphConfig.neighbor_depth,
      }),
    onSuccess: (data) => {
      setGraphResult(data);
    },
  });

  const reportMutation = useMutation({
    mutationFn: (title: string) =>
      generateKeywordGraphReport({
        title: title || undefined,
        post_ids: selectedPostIds,
        exclude_post_ids: excludedPostIds,
        graph_mode: graphConfig.graph_mode,
        include_neighbors: graphConfig.include_neighbors,
        neighbor_depth: graphConfig.neighbor_depth,
      }),
  });

  const toggleSelected = (postId: number) => {
    setSelectedPostIds((current) =>
      current.includes(postId) ? current.filter((value) => value !== postId) : [...current, postId],
    );
    setExcludedPostIds((current) => current.filter((value) => value !== postId));
  };

  const toggleExcluded = (postId: number) => {
    if (!selectedPostIds.includes(postId)) {
      return;
    }

    setExcludedPostIds((current) =>
      current.includes(postId) ? current.filter((value) => value !== postId) : [...current, postId],
    );
  };

  useEffect(() => {
    setGraphResult(null);
    buildMutation.reset();
    reportMutation.reset();
  }, [
    excludedKey,
    graphConfig.graph_mode,
    graphConfig.include_neighbors,
    graphConfig.neighbor_depth,
    selectedKey,
  ]);

  return {
    selectedPostIds,
    excludedPostIds,
    selectedItems,
    graphConfig,
    setGraphConfig,
    graphResult,
    setGraphResult,
    buildMutation,
    reportMutation,
    toggleSelected,
    toggleExcluded,
  };
}
