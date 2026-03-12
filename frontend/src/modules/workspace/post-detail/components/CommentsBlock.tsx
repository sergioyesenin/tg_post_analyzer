import type { ReactNode } from 'react';

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
  return (
    <DetailBlockShell eyebrow="comments" title="Comments" actionSlot={actionSlot}>
      {isLoading ? (
        <LoadingState title="Loading comments" description="Fetching post comments and thread metadata." />
      ) : isError ? (
        <ErrorState title="Comments failed to load" description="Comments block could not be loaded for this post." />
      ) : comments.length === 0 ? (
        <EmptyState title="No comments available" description="This post currently has no stored comments." />
      ) : (
        <div className="comment-thread-list">
          {comments.map((comment) => (
            <article key={comment.id} className="comment-thread-item" style={{ marginLeft: `${comment.depth * 18}px` }}>
              <div className="comment-thread-item__meta">
                <strong>Message #{comment.tgMessageId}</strong>
                <span>{comment.date}</span>
                {comment.threadModeHint ? <span>thread-aware</span> : null}
              </div>
              <p>{comment.text}</p>
            </article>
          ))}
        </div>
      )}
    </DetailBlockShell>
  );
}
