import type { PropsWithChildren } from 'react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();

  return (
    <div className="placeholder-grid">
      <EmptyState title={title} description={description} />

      <section className="placeholder-rail">
        <span className="state-card__eyebrow">{eyebrow}</span>
        <strong>{t('placeholders.foundationTitle')}</strong>
        <span>{t('placeholders.foundationDescription')}</span>
      </section>

      {partialState?.partial ? (
        <section className="placeholder-rail">
          <span className="state-card__eyebrow">{t('placeholders.partialEyebrow')}</span>
          <strong>{t('placeholders.partialTitle')}</strong>
          <span>{t('placeholders.partialDescription')}</span>
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
