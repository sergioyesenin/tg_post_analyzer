import { Link } from 'react-router-dom';

import { DetailBlockShell } from '@modules/workspace/post-detail/components/DetailBlockShell';
import type { LinkViewModel } from '@modules/workspace/post-detail/mappers';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type LinksBlockProps = {
  links: LinkViewModel[];
  isLoading: boolean;
  isError: boolean;
};

export function LinksBlock({ links, isLoading, isError }: LinksBlockProps) {
  return (
    <DetailBlockShell eyebrow="links" title="Links">
      {isLoading ? (
        <LoadingState title="Loading links" description="Fetching related post links for this post." />
      ) : isError ? (
        <ErrorState title="Links failed to load" description="Related links are unavailable for this post." />
      ) : links.length === 0 ? (
        <EmptyState title="No links found" description="The backend returned no related post links for this post." />
      ) : (
        <div className="detail-list">
          {links.map((link) => (
            <div key={link.id} className="detail-list__item">
              <div>
                <strong>{link.type}</strong>
                <p>
                  {link.direction} · score {link.score} · status {link.status}
                </p>
              </div>
              <div className="detail-list__actions">
                <span>{link.updatedAt}</span>
                <Link className="table-link" to={link.route}>
                  Open linked post
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </DetailBlockShell>
  );
}
