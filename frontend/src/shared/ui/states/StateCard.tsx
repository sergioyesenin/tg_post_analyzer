import type { PropsWithChildren } from 'react';

type StateCardProps = PropsWithChildren<{
  eyebrow?: string;
  title: string;
  description: string;
  tone?: 'default' | 'danger' | 'warning' | 'empty';
  meta?: string;
}>;

export function StateCard({
  eyebrow = 'system state',
  title,
  description,
  tone = 'default',
  meta,
  children,
}: StateCardProps) {
  return (
    <section className={`state-card state-card--${tone}`}>
      <span className="state-card__eyebrow">{eyebrow}</span>
      <h1 className="state-card__title">{title}</h1>
      <p className="state-card__description">{description}</p>
      {children}
      {meta ? <div className="state-card__meta">{meta}</div> : null}
    </section>
  );
}
