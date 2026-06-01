import { useTranslation } from 'react-i18next';
import { ApiError } from '@shared/api/client';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { usePostReportTrace } from '@modules/workspace/post-detail/hooks';
import { TraceExpandProvider, useTraceExpand } from './TraceExpandContext';
import { TraceGlobalIndicator } from './TraceGlobalIndicator';
import { TraceStepCard } from './TraceStepCard';
import { TraceRetrieval } from './TraceRetrieval';
import { TraceReview } from './TraceReview';
import { TraceEpistemicClaims } from './TraceEpistemicClaims';
import { ExpertOutput } from './ExpertOutput';

function TraceContent({ postId }: { postId: number }) {
  const { t } = useTranslation();
  const { data, isLoading, error } = usePostReportTrace(postId);
  const { expandedSteps, toggleStep, expandAll, collapseAll } = useTraceExpand();

  const copyTraceToClipboard = () => {
    if (data) {
      navigator.clipboard.writeText(JSON.stringify(data.trace, null, 2));
    }
  };

  const downloadTraceJson = () => {
    if (data) {
      const blob = new Blob([JSON.stringify(data.trace, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trace_post_${postId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  if (isLoading) {
    return <LoadingState title={t('trace.title')} description={t('common.loading')} />;
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <div className="trace-empty">{t('trace.no_trace')}</div>;
    }
    return <ErrorState title={t('trace.title')} description={t('common.error')} />;
  }

  if (!data) return null;

  const { trace } = data;
  const steps = trace.steps;

  const renderContext = (step: typeof steps.context) => (
    <div>
      {step.llm_context && (
        <>
          <p><strong>{t('trace.details_event_summary')}:</strong> {step.llm_context.event_summary}</p>
          <p><strong>{t('trace.details_article_focus')}:</strong> {step.llm_context.article_focus}</p>
          <details>
            <summary>{t('trace.details_data_quality')}</summary>
            <pre>{JSON.stringify(step.llm_context.data_quality, null, 2)}</pre>
            <pre>{JSON.stringify(step.llm_context.key_entities, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );

  const renderRouting = (step: typeof steps.routing) => (
    <div>
      {step.llm_routing && (
        <>
          <p><strong>{t('trace.details_primary_category')}:</strong> {step.llm_routing.primary_category}</p>
          <p><strong>{t('trace.details_routing_focus')}:</strong> {step.llm_routing.routing_focus}</p>
          <p><strong>{t('trace.confidence')}:</strong> {step.llm_routing.confidence}</p>
          <ul>
            {step.llm_routing.reasoning?.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </>
      )}
    </div>
  );

  const renderExpert = (step: typeof steps.expert) => (
    <div>
      {step.llm_expert && <ExpertOutput data={step.llm_expert} />}
    </div>
  );

  const renderPublicOpinion = (step: typeof steps.public_opinion) => (
    <div>
      {step.llm_public_opinion && (
        <>
          <p><strong>{t('trace.details_discussion_state')}:</strong> {step.llm_public_opinion.discussion_state}</p>
          <p><strong>{t('trace.confidence')}:</strong> {step.llm_public_opinion.confidence}</p>
          <details>
            <summary>{t('trace.details_main_topics')}</summary>
            <ul>{step.llm_public_opinion.main_topics?.map((t, i) => <li key={i}>{t}</li>)}</ul>
          </details>
          <details>
            <summary>{t('trace.details_dominant_reactions')}</summary>
            <ul>{step.llm_public_opinion.dominant_reactions?.map((r, i) => <li key={i}>{r.text} (conf: {r.confidence})</li>)}</ul>
          </details>
        </>
      )}
    </div>
  );

  const renderSynthesis = (step: typeof steps.synthesis) => (
    <div>
      {step.report_text && (
        <>
          <p><strong>{t('trace.details_report_text')}:</strong></p>
          <div className="trace-synthesis-text">{step.report_text}</div>
          <p className="trace-synthesis-meta">{t('trace.details_sentence_count')}: {step.sentence_count}</p>
        </>
      )}
    </div>
  );

  const renderReviewer = (step: typeof steps.reviewer) => (
    <div>
      <p><strong>{t('trace.decision')}:</strong> {step.decision || step.llm_reviewer?.decision}</p>
      {step.llm_reviewer?.issues && step.llm_reviewer.issues.length > 0 && (
        <p><strong>{t('trace.details_issues')}:</strong> {step.llm_reviewer.issues.join(', ')}</p>
      )}
      {step.history && step.history.length > 0 && (
        <details>
          <summary>{t('trace.history')} ({step.history.length})</summary>
          <ul>
            {step.history.map((item, idx) => (
              <li key={idx}>{item.decision} – {item.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );

  return (
    <div className="trace-section">
      <div className="trace-section__header">
        <h3>{t('trace.title')}</h3>
        <div className="trace-section__actions">
          <button className="dashboard-button dashboard-button--ghost" onClick={expandAll}>
            {t('trace.expand_all')}
          </button>
          <button className="dashboard-button dashboard-button--ghost" onClick={collapseAll}>
            {t('trace.collapse_all')}
          </button>
          <button className="dashboard-button dashboard-button--ghost" onClick={copyTraceToClipboard}>
            {t('trace.copy_trace')}
          </button>
          <button className="dashboard-button dashboard-button--ghost" onClick={downloadTraceJson}>
            {t('trace.download_json')}
          </button>
        </div>
      </div>

      <TraceGlobalIndicator trace={trace} />
      <TraceEpistemicClaims claims={trace.epistemic_claims} />

      <div className="trace-steps-list">
        <TraceStepCard
          title={t('trace.step_context')}
          step={steps.context}
          expanded={!!expandedSteps.context}
          onToggle={() => toggleStep('context')}
        >
          {renderContext(steps.context)}
        </TraceStepCard>

        <TraceStepCard
          title={t('trace.step_routing')}
          step={steps.routing}
          expanded={!!expandedSteps.routing}
          onToggle={() => toggleStep('routing')}
        >
          {renderRouting(steps.routing)}
        </TraceStepCard>

        <TraceStepCard
          title={t('trace.step_expert')}
          step={steps.expert}
          expanded={!!expandedSteps.expert}
          onToggle={() => toggleStep('expert')}
        >
          {renderExpert(steps.expert)}
        </TraceStepCard>

        <TraceStepCard
          title={t('trace.step_public_opinion')}
          step={steps.public_opinion}
          expanded={!!expandedSteps.public_opinion}
          onToggle={() => toggleStep('public_opinion')}
        >
          {renderPublicOpinion(steps.public_opinion)}
        </TraceStepCard>

        <TraceStepCard
          title={t('trace.step_synthesis')}
          step={steps.synthesis}
          expanded={!!expandedSteps.synthesis}
          onToggle={() => toggleStep('synthesis')}
        >
          {renderSynthesis(steps.synthesis)}
        </TraceStepCard>

        <TraceStepCard
          title={t('trace.step_reviewer')}
          step={steps.reviewer}
          expanded={!!expandedSteps.reviewer}
          onToggle={() => toggleStep('reviewer')}
        >
          {renderReviewer(steps.reviewer)}
        </TraceStepCard>
      </div>

      <TraceRetrieval retrieval={trace.retrieval} />
      <TraceReview review={trace.review} />
    </div>
  );
}

export function TraceSection({ postId }: { postId: number }) {
  return (
    <TraceExpandProvider>
      <TraceContent postId={postId} />
    </TraceExpandProvider>
  );
}