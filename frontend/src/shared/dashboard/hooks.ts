import { useLocation, useNavigate } from 'react-router-dom';

import type { DashboardMode } from '@shared/dashboard/contracts';
import {
  getDashboardModePath,
  parseDashboardFilters,
  serializeDashboardFilters,
  type DashboardFiltersByMode,
} from '@shared/dashboard/filters';

export function useDashboardFilters<TMode extends DashboardMode>(mode: TMode) {
  const location = useLocation();
  const navigate = useNavigate();
  const filters = parseDashboardFilters(mode, location.search);

  const applyFilters = (nextFilters: DashboardFiltersByMode[TMode]) => {
    const search = serializeDashboardFilters(mode, nextFilters);
    navigate({
      pathname: getDashboardModePath(mode),
      search: search ? `?${search}` : '',
    });
  };

  const resetFilters = () => {
    navigate({
      pathname: getDashboardModePath(mode),
      search: '',
    });
  };

  const applySearch = (query: string) => {
    const search = serializeDashboardFilters(mode, {
      ...filters,
      query,
    });

    navigate({
      pathname: getDashboardModePath(mode),
      search: search ? `?${search}` : '',
    });
  };

  const resetSearch = () => {
    const search = serializeDashboardFilters(mode, {
      ...filters,
      query: '',
    });

    navigate({
      pathname: getDashboardModePath(mode),
      search: search ? `?${search}` : '',
    });
  };

  return {
    filters,
    applyFilters,
    resetFilters,
    applySearch,
    resetSearch,
  };
}
