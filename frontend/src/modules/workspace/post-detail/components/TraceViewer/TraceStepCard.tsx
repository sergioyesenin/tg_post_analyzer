import { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { StepDetail } from '../../contracts';

interface TraceStepCardProps {
  title: string;
  step: StepDetail;
  expanded: boolean;
  onToggle: () => void;
  children?: ReactNode;
}

export function TraceStepCard({ title, step, expanded, onToggle, children }: TraceStepCardProps) {
  const { t } = useTranslation();

  const statusColor =
    step.status === 'completed' ? 'success' : step.status === 'failed' ? 'danger' : 'warning';

  const hasMalformed = step.malformed_output === true;

  const runCountLabel =
    step.run_count === 1
      ? t('trace.run_count', { count: step.run_count })
      : t('trace.run_count_plural', { count: step.run_count });

  return (
    <div className={`trace-step-card ${hasMalformed ? 'trace-step-card--warning' : ''}`}>
      <div className="trace-step-card__header" onClick={onToggle}>
        <div className="trace-step-card__title">
          <span className="trace-step-card__name">{title}</span>
          <span className={`status-badge status-badge--${statusColor}`}>
            {t(`trace.status_${step.status}`, step.status)}
          </span>
          <span className={`trace-step-card__run-count ${step.run_count > 1 ? 'trace-step-card__run-count--warn' : ''}`}>
            {runCountLabel}
          </span>
          {hasMalformed && <span className="trace-step-card__warning-icon">{t('trace.malformed_output')}</span>}
        </div>
        <button className="trace-step-card__expand" aria-label={expanded ? t('trace.collapse_all') : t('trace.expand_all')}>
          {expanded ? '−' : '+'}
        </button>
      </div>
      {expanded && <div className="trace-step-card__content">{children}</div>}
    </div>
  );
}