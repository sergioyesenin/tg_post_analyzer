import type { PropsWithChildren, ReactNode } from 'react';

type DetailBlockShellProps = PropsWithChildren<{
  eyebrow: string;
  title: string;
  actionSlot?: ReactNode;
}>;

export function DetailBlockShell({ eyebrow, title, actionSlot, children }: DetailBlockShellProps) {
  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{eyebrow}</span>
          <strong>{title}</strong>
        </div>
        {actionSlot}
      </div>
      {children}
    </section>
  );
}
