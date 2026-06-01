import type { ChannelDto } from '@modules/admin/contracts';
import type {
  EventsDashboardResponse,
  PostsDashboardResponse,
  ProcessesDashboardResponse,
} from '@shared/dashboard/contracts';
import type { DashboardFiltersByMode } from '@shared/dashboard/filters';

export type DashboardFilterOption<TValue extends string | number> = {
  value: TValue;
  label: string;
  description?: string | null;
};

export type DashboardFilterOptionsByMode = {
  posts: {
    channel_ids: DashboardFilterOption<number>[];
    categories: DashboardFilterOption<string>[];
    report_status: DashboardFilterOption<string>[];
  };
  events: {
    status: DashboardFilterOption<string>[];
    channel_ids: DashboardFilterOption<number>[];
    categories: DashboardFilterOption<string>[];
  };
  processes: {
    status: DashboardFilterOption<string>[];
  };
};

function sortTextValues(values: Iterable<string>) {
  return [...new Set(values)]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
}

function formatChannelLabel(channel: ChannelDto) {
  const title = channel.title?.trim();
  if (title) {
    return title;
  }

  return `@${channel.username}`;
}

function formatChannelDescription(channel: ChannelDto) {
  const parts = [`#${channel.id}`];

  if (channel.title?.trim()) {
    parts.push(`@${channel.username}`);
  }

  if (channel.category?.trim()) {
    parts.push(channel.category.trim());
  }

  return parts.join(' | ');
}

function normalizeChannels(channels: ChannelDto[] | undefined): ChannelDto[] {
  return Array.isArray(channels) ? channels : [];
}

function buildChannelOptions(channels: ChannelDto[] | undefined, selectedIds: number[]) {
  const knownChannels = [...normalizeChannels(channels)].sort((left, right) =>
    formatChannelLabel(left).localeCompare(formatChannelLabel(right)),
  );
  const selectedIdSet = new Set(selectedIds);
  const options = knownChannels.map((channel) => ({
    value: channel.id,
    label: formatChannelLabel(channel),
    description: formatChannelDescription(channel),
  }));

  selectedIds.forEach((channelId) => {
    if (knownChannels.some((channel) => channel.id === channelId)) {
      return;
    }

    options.push({
      value: channelId,
      label: `Channel #${channelId}`,
      description: `#${channelId}`,
    });
  });

  return options.sort((left, right) => {
    const leftSelected = selectedIdSet.has(left.value);
    const rightSelected = selectedIdSet.has(right.value);

    if (leftSelected !== rightSelected) {
      return leftSelected ? -1 : 1;
    }

    return left.label.localeCompare(right.label);
  });
}

function buildCategoryOptions(channels: ChannelDto[] | undefined, selectedCategories: string[]) {
  const values = sortTextValues([...normalizeChannels(channels).map((channel) => channel.category?.trim() ?? ''), ...selectedCategories]);

  return values.map((value) => ({
    value,
    label: value,
    description: null,
  }));
}

function buildStringOptions(values: Iterable<string>, selectedValues: string[]) {
  return sortTextValues([...values, ...selectedValues]).map((value) => ({
    value,
    label: value,
    description: null,
  }));
}

export function getPostsDashboardFilterOptions(params: {
  filters: DashboardFiltersByMode['posts'];
  dashboardData: PostsDashboardResponse | null;
  channels?: ChannelDto[];
}): DashboardFilterOptionsByMode['posts'] {
  const { filters, dashboardData, channels } = params;

  return {
    channel_ids: buildChannelOptions(channels, filters.channel_ids),
    categories: buildCategoryOptions(channels, filters.categories),
    report_status: buildStringOptions(
      ['missing', 'pending', 'draft', 'ready', 'limited', 'insufficient_data', 'failed', ...(dashboardData?.items.map((item) => item.report_status) ?? [])],
      filters.report_status,
    ),
  };
}

export function getEventsDashboardFilterOptions(params: {
  filters: DashboardFiltersByMode['events'];
  dashboardData: EventsDashboardResponse | null;
  channels?: ChannelDto[];
}): DashboardFilterOptionsByMode['events'] {
  const { filters, dashboardData, channels } = params;

  return {
    status: buildStringOptions(dashboardData?.items.map((item) => item.status) ?? [], filters.status),
    channel_ids: buildChannelOptions(channels, filters.channel_ids),
    categories: buildCategoryOptions(channels, filters.categories),
  };
}

export function getProcessesDashboardFilterOptions(params: {
  filters: DashboardFiltersByMode['processes'];
  dashboardData: ProcessesDashboardResponse | null;
}): DashboardFilterOptionsByMode['processes'] {
  const { filters, dashboardData } = params;

  return {
    status: buildStringOptions(dashboardData?.items.map((item) => item.status) ?? [], filters.status),
  };
}

