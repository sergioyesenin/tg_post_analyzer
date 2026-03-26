import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { DetailBlockShell } from '@modules/workspace/post-detail/components/DetailBlockShell';
import type { LinkViewModel } from '@modules/workspace/post-detail/mappers';
import { QueryActivityNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type LinksBlockProps = {
  links: LinkViewModel[];
  isLoading: boolean;
  isRefreshing: boolean;
  isError: boolean;
  showErrorNotice: boolean;
};

export function LinksBlock({ links, isLoading, isRefreshing, isError, showErrorNotice }: LinksBlockProps) {
  const { t } = useTranslation();

  return (
    <DetailBlockShell eyebrow={t('posts.links.eyebrow')} title={t('posts.links.title')}>
      {isRefreshing ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('posts.links.refreshingTitle', { defaultValue: 'Связи обновляются' })}
          description={t('posts.links.refreshingDescription', { defaultValue: 'Текущие связи остаются видимыми до завершения запроса.' })}
        />
      ) : null}
      {showErrorNotice ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('posts.links.refreshErrorTitle', { defaultValue: 'Не удалось обновить связи' })}
          description={t('posts.links.refreshErrorDescription', { defaultValue: 'Последний успешный список связей сохранен на экране.' })}
          tone="danger"
        />
      ) : null}
      {isLoading ? (
        <LoadingState title={t('posts.links.loadingTitle')} description={t('posts.links.loadingDescription')} />
      ) : isError ? (
        <ErrorState title={t('posts.links.errorTitle')} description={t('posts.links.errorDescription')} />
      ) : links.length === 0 ? (
        <EmptyState title={t('posts.links.emptyTitle')} description={t('posts.links.emptyDescription')} />
      ) : (
        <div className="detail-list">
          {links.map((link) => (
            <div key={link.id} className="detail-list__item">
              <div>
                <strong>{link.type}</strong>
                <p>
                  {link.direction} | {t('posts.links.score', { value: link.score })} | {t('posts.links.status', { value: link.status })}
                </p>
              </div>
              <div className="detail-list__actions">
                <span>{link.updatedAt}</span>
                <Link className="table-link" to={link.route}>
                  {t('posts.links.openLinkedPost')}
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </DetailBlockShell>
  );
}
