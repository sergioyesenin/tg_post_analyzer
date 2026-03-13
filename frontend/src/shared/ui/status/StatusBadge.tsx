import type { ReactNode } from 'react';

import type { StatusMeta } from '@shared/ui/status/statusMeta';

type StatusBadgeProps = {
  meta: StatusMeta;
  ariaLabel?: string;
  suffix?: ReactNode;
};

export function StatusBadge({ meta, ariaLabel, suffix }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-badge--${meta.tone}`} aria-label={ariaLabel ?? meta.label}>
      {meta.label}
      {suffix}
    </span>
  );
}
