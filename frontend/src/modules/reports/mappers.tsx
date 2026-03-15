import { Link } from 'react-router-dom';

import { i18n } from '@shared/i18n/i18n';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import { formatUtcDateTime } from '@shared/utils/formatters';
import type {
  EventReportListItemDto,
  PostReportListItemDto,
  ProcessReportListItemDto,
  ReportType,
  ReportsListResponseByType,
} from '@modules/reports/contracts';

export function getReportsColumnsByType(): Record<ReportType, DashboardTableColumn[]> {
  return {
    posts: [
      { id: 'entity', label: i18n.t('reports.columns.post', { defaultValue: 'Пост' }) },
      { id: 'context', label: i18n.t('reports.columns.context', { defaultValue: 'Контекст' }) },
      { id: 'status', label: i18n.t('fields.status') },
      { id: 'created_at', label: i18n.t('reports.columns.created', { defaultValue: 'Создан' }) },
      { id: 'actions', label: i18n.t('reports.columns.actions', { defaultValue: 'Действия' }) },
    ],
    events: [
      { id: 'entity', label: i18n.t('reports.columns.event', { defaultValue: 'Событие' }) },
      { id: 'version', label: i18n.t('reports.columns.version', { defaultValue: 'Версия' }) },
      { id: 'status', label: i18n.t('fields.status') },
      { id: 'created_at', label: i18n.t('reports.columns.created', { defaultValue: 'Создан' }) },
      { id: 'actions', label: i18n.t('reports.columns.actions', { defaultValue: 'Действия' }) },
    ],
    processes: [
      { id: 'entity', label: i18n.t('reports.columns.process', { defaultValue: 'Процесс' }) },
      { id: 'version', label: i18n.t('reports.columns.version', { defaultValue: 'Версия' }) },
      { id: 'status', label: i18n.t('fields.status') },
      { id: 'created_at', label: i18n.t('reports.columns.created', { defaultValue: 'Создан' }) },
      { id: 'actions', label: i18n.t('reports.columns.actions', { defaultValue: 'Действия' }) },
    ],
  };
}

function mapPostRow(item: PostReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{i18n.t('reports.rows.postLabel', { id: item.post_id, defaultValue: `Пост #${item.post_id}` })}</strong>
          <span>{formatUtcDateTime(item.post_date)}</span>
        </div>
      ),
      context: (
        <div className="dashboard-table-shell__cell-stack">
          <span>{item.channel_username ? `@${item.channel_username}` : i18n.t('reports.rows.channelLabel', { id: item.channel_id, defaultValue: `Канал #${item.channel_id}` })}</span>
          <span>{item.channel_category ?? i18n.t('common.na')}</span>
        </div>
      ),
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/posts/${item.post_id}`}>
            {i18n.t('reports.rows.openPost', { defaultValue: 'Открыть пост' })}
          </Link>
        </div>
      ),
    },
  };
}

function mapEventRow(item: EventReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{item.event_title ?? i18n.t('reports.rows.eventFallback', { id: item.event_id, defaultValue: `Событие ${item.event_id}` })}</strong>
          <span>{i18n.t('reports.rows.eventLabel', { id: item.event_id, defaultValue: `Событие #${item.event_id}` })}</span>
        </div>
      ),
      version: item.version ?? i18n.t('common.na'),
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/events/${item.event_id}`}>
            {i18n.t('reports.rows.openEvent', { defaultValue: 'Открыть событие' })}
          </Link>
        </div>
      ),
    },
  };
}

function mapProcessRow(item: ProcessReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{item.process_title ?? i18n.t('reports.rows.processFallback', { id: item.process_id, defaultValue: `Процесс ${item.process_id}` })}</strong>
          <span>{i18n.t('reports.rows.processLabel', { id: item.process_id, defaultValue: `Процесс #${item.process_id}` })}</span>
        </div>
      ),
      version: item.version ?? i18n.t('common.na'),
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/processes/${item.process_id}`}>
            {i18n.t('reports.rows.openProcess', { defaultValue: 'Открыть процесс' })}
          </Link>
        </div>
      ),
    },
  };
}

export function mapReportsRowsToTableRows<TType extends ReportType>(
  type: TType,
  items: ReportsListResponseByType[TType],
): DashboardTableRow[] {
  if (type === 'posts') {
    return (items as ReportsListResponseByType['posts']).map(mapPostRow);
  }

  if (type === 'events') {
    return (items as ReportsListResponseByType['events']).map(mapEventRow);
  }

  return (items as ReportsListResponseByType['processes']).map(mapProcessRow);
}

export function getReportsCopyByType(): Record<
  ReportType,
  { title: string; tableTitle: string; description: string; emptyTitle: string; emptyDescription: string }
> {
  return {
    posts: {
      title: i18n.t('reports.types.posts.title', { defaultValue: 'Отчеты по постам' }),
      tableTitle: i18n.t('reports.types.posts.tableTitle', { defaultValue: 'Таблица отчетов по постам' }),
      description: i18n.t('reports.types.posts.description', { defaultValue: 'Каталог отчетов по постам поддерживает фильтрацию по каналу и дате, а также пакетную генерацию черновиков для доступных ролей.' }),
      emptyTitle: i18n.t('reports.types.posts.emptyTitle', { defaultValue: 'Нет отчетов по постам для текущих фильтров' }),
      emptyDescription: i18n.t('reports.types.posts.emptyDescription', { defaultValue: 'Список отчетов успешно загрузился, но по текущему набору фильтров подходящих отчетов нет.' }),
    },
    events: {
      title: i18n.t('reports.types.events.title', { defaultValue: 'Отчеты по событиям' }),
      tableTitle: i18n.t('reports.types.events.tableTitle', { defaultValue: 'Таблица отчетов по событиям' }),
      description: i18n.t('reports.types.events.description', { defaultValue: 'Каталог отчетов по событиям помогает просматривать черновики и готовые отчеты на уровне событий.' }),
      emptyTitle: i18n.t('reports.types.events.emptyTitle', { defaultValue: 'Нет отчетов по событиям для текущих фильтров' }),
      emptyDescription: i18n.t('reports.types.events.emptyDescription', { defaultValue: 'Список отчетов успешно загрузился, но по текущему набору фильтров подходящих отчетов нет.' }),
    },
    processes: {
      title: i18n.t('reports.types.processes.title', { defaultValue: 'Отчеты по процессам' }),
      tableTitle: i18n.t('reports.types.processes.tableTitle', { defaultValue: 'Таблица отчетов по процессам' }),
      description: i18n.t('reports.types.processes.description', { defaultValue: 'Каталог отчетов по процессам хранит версии процессных отчетов и быстрые переходы в детали процесса.' }),
      emptyTitle: i18n.t('reports.types.processes.emptyTitle', { defaultValue: 'Нет отчетов по процессам для текущих фильтров' }),
      emptyDescription: i18n.t('reports.types.processes.emptyDescription', { defaultValue: 'Список отчетов успешно загрузился, но по текущему набору фильтров подходящих отчетов нет.' }),
    },
  };
}
