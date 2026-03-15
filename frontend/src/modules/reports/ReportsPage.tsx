import { NavLink, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { canPerformAction } from '@shared/routing/policy';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { ReportsActionBar } from '@modules/reports/components/ReportsActionBar';
import { ReportsFilterBar } from '@modules/reports/components/ReportsFilterBar';
import { ReportsTableSection } from '@modules/reports/components/ReportsTableSection';
import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';
import { useGeneratePostReportsByFilterAction, useReportsFilters, useReportsListQuery } from '@modules/reports/hooks';
import { getReportsCopyByType } from '@modules/reports/mappers';

function isReportType(value: string | undefined): value is ReportType {
  return value === 'posts' || value === 'events' || value === 'processes';
}

export function ReportsPage() {
  const { t } = useTranslation();
  const { reportType } = useParams();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];

  if (!isReportType(reportType)) {
    return <ErrorState title={t('reports.invalidTitle', { defaultValue: 'Неизвестный каталог отчетов' })} description={t('reports.invalidDescription', { defaultValue: 'Запрошенный маршрут отчетов не поддерживается.' })} />;
  }

  const type = reportType;
  const copy = getReportsCopyByType()[type];
  const { filters, applyFilters, resetFilters } = useReportsFilters(type);
  const listQuery = useReportsListQuery(type, filters);
  const canGenerateBatch = type === 'posts' && canPerformAction('reports.generate', roles);
  const postBatchFilters: ReportsFiltersByType['posts'] =
    type === 'posts'
      ? (filters as ReportsFiltersByType['posts'])
      : { channel_ids: [], categories: [], date_from: '', date_to: '', min_comments: null, limit: 100, offset: 0 };
  const postBatchAction = useGeneratePostReportsByFilterAction(postBatchFilters);
  const batchAction = type === 'posts' ? postBatchAction : null;

  if (listQuery.isLoading) {
    return <LoadingState title={t('reports.loadingTitle', { defaultValue: 'Загрузка каталога отчетов' })} description={t('reports.loadingDescription', { defaultValue: 'Получаем выбранный каталог отчетов.' })} />;
  }

  if (listQuery.isError) {
    const error = listQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return (
        <ForbiddenState
          title={t('reports.restrictedTitle', { defaultValue: 'Каталог отчетов недоступен' })}
          description={t('reports.restrictedDescription', { defaultValue: 'Маршрут виден, но backend отклонил доступ к этому каталогу отчетов.' })}
        />
      );
    }

    return <ErrorState title={t('reports.errorTitle', { defaultValue: 'Не удалось загрузить каталог отчетов' })} description={t('reports.errorDescription', { defaultValue: 'Запрос списка отчетов завершился ошибкой.' })} />;
  }

  const items = listQuery.data ?? [];

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">{t('states.reports')}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="dashboard-page__meta">
          <nav className="process-graph-toolbar__meta" aria-label={t('navigation.reportTypes')}>
            <NavLink className="table-link" to="/reports/posts">
              {t('navigation.posts')}
            </NavLink>
            <NavLink className="table-link" to="/reports/events">
              {t('navigation.events')}
            </NavLink>
            <NavLink className="table-link" to="/reports/processes">
              {t('navigation.processes')}
            </NavLink>
          </nav>
        </div>
      </section>

      <ReportsFilterBar type={type} filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice
          title={t('reports.readOnlyTitle', { defaultValue: 'Для viewer каталог отчетов доступен только для чтения' })}
          description={t('reports.readOnlyDescription', { defaultValue: 'Просмотр списка и экспорт доступны, а пакетная генерация и другие мутации скрыты.' })}
          ariaLabel="reports.readOnly"
        />
      ) : null}

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <ReportsTableSection type={type} items={items} />
        </div>
        <div className="dashboard-page__secondary">
          <ReportsActionBar type={type} filters={filters} canGenerateBatch={canGenerateBatch} batchAction={batchAction} />
        </div>
      </section>
    </div>
  );
}
