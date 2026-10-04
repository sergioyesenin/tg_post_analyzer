import { useTranslation } from 'react-i18next';
import { ApiError } from '@shared/api/client';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { usePostReportTrace } from '@modules/workspace/post-detail/hooks';
import { TraceExpandProvider, useTraceExpand } from './TraceExpandContext';
import { TraceGlobalIndicator } from './TraceGlobalIndicator';
import { TraceStepCard } from './TraceStepCard';
import { TraceRetrieval } from './TraceRetrieval';
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
            <div className="data-quality-block">
              <div className="data-quality-item">
                <span>Комментарии присутствуют:</span>
                <strong>{step.llm_context.data_quality.comments_present ? '✅ Да' : '❌ Нет'}</strong>
              </div>
              <div className="data-quality-item">
                <span>Статья достаточна:</span>
                <strong>{step.llm_context.data_quality.article_sufficient ? '✅ Да' : '❌ Нет'}</strong>
              </div>
              {step.llm_context.data_quality.issues?.length > 0 && (
                <div className="data-quality-item">
                  <span>Проблемы:</span>
                  <strong>{step.llm_context.data_quality.issues.join(', ')}</strong>
                </div>
              )}
            </div>

            <div className="entities-block">
              {Object.entries(step.llm_context.key_entities).map(([key, values]) => {
                if (!values || values.length === 0) return null;
                return (
                  <div key={key} className="entity-group">
                    <h6>{key === 'persons' ? 'Люди' : key === 'locations' ? 'Локации' : key === 'organizations' ? 'Организации' : 'Платформы'}</h6>
                    <div>
                      {values.map((item, idx) => (
                        <span key={idx} className="entity-tag">{item}</span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
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
          
          {/* НОВО: поисковые запросы */}
          {step.search_queries && step.search_queries.length > 0 && (
            <details>
              <summary>Поисковые запросы ({step.search_queries.length})</summary>
              <ul className="search-queries-list">
                {step.search_queries.map((q, idx) => (
                  <li key={idx}>
                    <code>{q.text}</code> <span className="query-type">[{q.type}]</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          
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

          {step.data_status && <p><strong>Статус данных:</strong> {step.data_status}</p>}
          {step.malformed_output && <p className="warning-text">⚠️ Некорректный вывод LLM</p>}

          {/* Социальные эффекты */}
          {step.social_effects && step.social_effects.length > 0 && (
            <details>
              <summary>Социальные эффекты</summary>
              <ul>
                {step.social_effects.map((item, idx) => {
                  if (typeof item === 'string') {
                    return <li key={idx}>{item}</li>;
                  }
                  if (typeof item === 'object' && item !== null && 'effect' in item) {
                    return (
                      <li key={idx}>
                        <strong>{item.effect}</strong>: {item.description}
                      </li>
                    );
                  }
                  return <li key={idx}>{String(item)}</li>;
                })}
              </ul>
            </details>
          )}

          {/* Доминирующие реакции */}
          {step.dominant_reactions && step.dominant_reactions.length > 0 && (
            <details>
              <summary>Доминирующие реакции</summary>
              <ul>
                {step.dominant_reactions.map((reaction, idx) => {
                  if (typeof reaction === 'string') {
                    return <li key={idx}>{reaction}</li>;
                  }
                  if (typeof reaction === 'object' && reaction !== null && 'type' in reaction) {
                    return (
                      <li key={idx}>
                        {reaction.type}: {reaction.description}
                        {reaction.confidence !== undefined && ` (уверенность: ${reaction.confidence})`}
                      </li>
                    );
                  }
                  return <li key={idx}>{String(reaction)}</li>;
                })}
              </ul>
            </details>
          )}

          {/* Основные темы */}
          <details>
            <summary>{t('trace.details_main_topics')}</summary>
            <ul>
              {step.llm_public_opinion.main_topics?.map((topic, i) => {
                if (typeof topic === 'string') {
                  return <li key={i}>{topic}</li>;
                }
                return (
                  <li key={i}>
                    <strong>{topic.topic}</strong>
                    {topic.subtopics && topic.subtopics.length > 0 && (
                      <ul>
                        {topic.subtopics.map((sub, j) => (
                          <li key={j}>{sub}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
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
          
          {/* НОВО: метрики качества */}
          {step.quality && <p><strong>Качество синтеза:</strong> {step.quality}</p>}
          {step.components && (
            <details>
              <summary>Компоненты отчёта</summary>
              <ul>
                {Object.entries(step.components).map(([key, included]) => (
                  <li key={key}>{key}: {included ? '✅' : '❌'}</li>
                ))}
              </ul>
            </details>
          )}
          {step.confidence_reason && <p><strong>Обоснование уверенности:</strong> {step.confidence_reason}</p>}
          {step.rerun_requested && <p className="warning-text">⚠️ Был запрошен повторный запуск</p>}
        </>
      )}
    </div>
  );

  const renderReviewer = (step: typeof steps.reviewer) => (
    <div>
      <p><strong>{t('trace.decision')}:</strong> {step.decision || step.llm_reviewer?.decision}</p>
      {step.rerun_iterations && <p><strong>Повторных запусков:</strong> {step.rerun_iterations}</p>}
      {step.llm_reviewer?.rerun_target && <p><strong>Цель перезапуска:</strong> {step.llm_reviewer.rerun_target}</p>}
      {step.llm_reviewer?.issues && step.llm_reviewer.issues.length > 0 && (
        <p><strong>{t('trace.details_issues')}:</strong> {step.llm_reviewer.issues.join(', ')}</p>
      )}
      {step.history && step.history.length > 0 && (
        <details>
          <summary>{t('trace.history')} ({step.history.length})</summary>
          <ul>
            {step.history.map((item, idx) => (
              <li key={idx}>
                {item.decision} – {item.reason}
                {item.target && ` (цель: ${item.target})`}
              </li>
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

        <TraceRetrieval retrieval={trace.retrieval} />

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