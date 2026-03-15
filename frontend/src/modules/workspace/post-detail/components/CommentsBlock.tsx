import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { CommentViewModel } from '@modules/workspace/post-detail/mappers';
import { DetailBlockShell } from '@modules/workspace/post-detail/components/DetailBlockShell';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type CommentsBlockProps = {
  comments: CommentViewModel[];
  isLoading: boolean;
  isError: boolean;
  actionSlot?: ReactNode;
};

export function CommentsBlock({ comments, isLoading, isError, actionSlot }: CommentsBlockProps) {
  const { t } = useTranslation();

  return (
    <DetailBlockShell eyebrow={t('posts.comments.eyebrow')} title={t('posts.comments.title')} actionSlot={actionSlot}>
      {isLoading ? (
        <LoadingState title={t('posts.comments.loadingTitle')} description={t('posts.comments.loadingDescription')} />
      ) : isError ? (
        <ErrorState title={t('posts.comments.errorTitle')} description={t('posts.comments.errorDescription')} />
      ) : comments.length === 0 ? (
        <EmptyState title={t('posts.comments.emptyTitle')} description={t('posts.comments.emptyDescription')} />
      ) : (
        <div className="comment-thread-list">
          {comments.map((comment) => (
            <article key={comment.id} className="comment-thread-item" style={{ marginLeft: `${comment.depth * 18}px` }}>
              <div className="comment-thread-item__meta">
                <strong>{t('posts.comments.messageTitle', { id: comment.tgMessageId })}</strong>
                <span>{comment.date}</span>
                {comment.threadModeHint ? <span>{t('posts.comments.threadAware')}</span> : null}
              </div>
              <p>{comment.text}</p>
            </article>
          ))}
        </div>
      )}
    </DetailBlockShell>
  );
}
