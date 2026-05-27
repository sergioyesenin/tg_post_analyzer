import { useTranslation } from 'react-i18next';
import { MultiAgentTrace } from '../../contracts';

function hasMalformedOutput(trace: MultiAgentTrace): boolean {
  const steps = trace.steps;
  const check = (obj: any) =>
    obj?.malformed_output === true ||
    (obj?.llm_expert && typeof obj.llm_expert === 'string' && obj.llm_expert.includes('":[{')) ||
    (obj?.llm_reviewer?.issues && obj.llm_reviewer.issues.length > 0);
  return (
    check(steps.context) ||
    check(steps.routing) ||
    check(steps.expert) ||
    check(steps.public_opinion) ||
    check(steps.synthesis) ||
    check(steps.reviewer)
  );
}

function hasRetries(trace: MultiAgentTrace): boolean {
  return Object.values(trace.steps).some(step => step.run_count > 1);
}

export function TraceGlobalIndicator({ trace }: { trace: MultiAgentTrace }) {
  const { t } = useTranslation();
  const allCompleted = Object.values(trace.steps).every(step => step.status === 'completed');
  const hasFailed = Object.values(trace.steps).some(step => step.status === 'failed');
  const hasRunning = Object.values(trace.steps).some(step => step.status === 'running');
  const malformed = hasMalformedOutput(trace);
  const retries = hasRetries(trace);

  if (hasRunning) {
    return <div className="trace-global-status trace-global-status--running">{t('trace.status_running')}</div>;
  }
  if (hasFailed) {
    return <div className="trace-global-status trace-global-status--failed">{t('trace.status_failed')}</div>;
  }
  if (malformed || retries) {
    return <div className="trace-global-status trace-global-status--warning">{t('trace.status_issues')}</div>;
  }
  if (allCompleted) {
    return <div className="trace-global-status trace-global-status--healthy">{t('trace.status_healthy')}</div>;
  }
  return null;
}