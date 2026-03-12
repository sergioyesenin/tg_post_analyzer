import type { PropsWithChildren } from 'react';

import type { DashboardWarning, PartialDashboardState } from '@shared/types/dashboard';
import { EmptyState } from '@shared/ui/states/EmptyState';

type RoutePlaceholderProps = PropsWithChildren<{
  eyebrow: string;
  title: string;
  description: string;
  warnings?: DashboardWarning[];
  partialState?: PartialDashboardState;
}>;

export function RoutePlaceholder({
  eyebrow,
  title,
  description,
  warnings = [],
  partialState,
  children,
}: RoutePlaceholderProps) {
  return (
    <div className="placeholder-grid">
      <EmptyState title={title} description={description} />

      <section className="placeholder-rail">
        <span className="state-card__eyebrow">{eyebrow}</span>
        <strong>Foundation blocks</strong>
        <span>App shell, providers, router and shared state contracts are wired in this stage.</span>
      </section>

      {partialState?.partial ? (
        <section className="placeholder-rail">
          <span className="state-card__eyebrow">partial data contract</span>
          <strong>Warnings remain non-blocking</strong>
          <span>Dashboard screens must stay usable when `partial=true`.</span>
          <ul className="warning-list">
            {(warnings.length ? warnings : partialState.warnings).map((warning) => (
              <li key={warning.code}>{warning.message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {children}
    </div>
  );
}
