import { JobStatusInline } from '@shared/ui/status/JobStatusInline';

type AsyncActionIndicatorProps = {
  title: string;
  description: string;
  status: string;
  jobId?: number | null;
  resultSummary?: string | null;
  tone?: 'default' | 'danger' | 'success';
};

export function AsyncActionIndicator({
  title,
  description,
  status,
  jobId,
  resultSummary,
  tone = 'default',
}: AsyncActionIndicatorProps) {
  return (
    <section className={`async-indicator async-indicator--${tone}`}>
      <div className="async-indicator__header">
        <strong>{title}</strong>
        <JobStatusInline status={status} jobId={jobId} />
      </div>
      <p>{description}</p>
      {resultSummary ? <span className="async-indicator__result">{resultSummary}</span> : null}
    </section>
  );
}
