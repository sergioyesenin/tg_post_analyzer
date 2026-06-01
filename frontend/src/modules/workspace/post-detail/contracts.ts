import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export type PostDetailDto = {
  id: number;
  channel_id: number;
  text: string | null;
  date: string;
  comments_count: number;
  views: number | null;
  involvement: number | null;
};

export type CommentDto = {
  id: number;
  post_id: number;
  tg_message_id: number;
  parent_tg_message_id: number | null;
  parent_comment_id: number | null;
  thread_root_tg_message_id: number | null;
  depth: number;
  text: string;
  date: string;
};

export type ReportDto = {
  id: number;
  post_id: number;
  status: string;
  content: string | null;
  report_json: Record<string, unknown> | null;
  created_at: string;
};

export type LinkDto = {
  id: number;
  src_post_id: number;
  dst_post_id: number;
  link_type: string;
  direction: string;
  score: number | null;
  status: string;
  evidence_json: Record<string, unknown> | null;
  model_version: string | null;
  pipeline_version: string | null;
  created_at: string;
  updated_at: string;
};

export type PostLinksDto = {
  post_id: number;
  links: LinkDto[];
};

export type PostDetailQueryBundle = {
  post: PostDetailDto;
  comments: CommentDto[];
  report: ReportDto | null;
  links: PostLinksDto;
};

export type PostDetailMutationResponse = AcceptedJobResponse;

export interface ReportTraceOut {
  entity_type: 'post';
  entity_id: number;
  report_id: number;
  version: string | null;
  status: string;
  trace: MultiAgentTrace;
  created_at: string;
}

export interface MultiAgentTrace {
  version: string;
  status: string;
  epistemic_claims: EpistemicClaim[];
  steps: TraceSteps;
  retrieval: RetrievalInfo;
  review: ReviewInfo;
}

export interface EpistemicClaim {
  text: string;
  type: 'fact' | 'derived' | 'uncertain' | 'external';
  source: string;
  confidence: number;
}

export interface TraceSteps {
  context: StepDetail;
  routing: StepDetail;
  expert: StepDetail;
  public_opinion: StepDetail;
  synthesis: StepDetail;
  reviewer: StepDetail;
}

export interface StepDetail {
  status: string;
  run_count: number;
  provenance_source?: string;
  provenance?: Record<string, unknown>;
  // Поля для разных шагов
  llm_context?: {
    event_summary: string;
    data_quality: Record<string, unknown>;
    key_entities: Record<string, unknown>;
    article_focus: string;
  };
  llm_routing?: {
    reasoning: string[];
    confidence: number;
    routing_focus: string;
    primary_category: string;
  };
  llm_expert?: Record<string, unknown>;
  llm_public_opinion?: {
    confidence: number;
    main_topics: string[];
    social_effects: string[];
    discussion_state: string;
    dominant_reactions: Array<{
      text: string;
      type: string;
      confidence: number;
    }>;
  };
  report_text?: string;
  sentence_count?: number;
  // Для reviewer
  decision?: string;
  llm_reviewer?: {
    decision?: string;
    issues?: string[];
    rerun_target?: string;
    [key: string]: unknown;
  };
  history?: Array<{
    reason: string;
    target: string;
    decision: string;
    iteration: number;
    confidence: number;
  }>;
  [key: string]: unknown; // запасной вариант
}

export interface RetrievalInfo {
  required: boolean;
  used: boolean;
  status: string;
  decision_inputs: Record<string, unknown>;
  decision_source: string;
  sources: RetrievalSource[];
}

export interface RetrievalSource {
  tier: string;
  score: number;
  title: string;
  domain: string;
  source: string;
  supports: string;
  freshness: number;
  relevance: number;
  content_quality: number;
  source_authority: number;
}

export interface ReviewInfo {
  iterations: number;
  history: Array<{
    reason: string;
    target: string;
    decision: string;
    iteration: number;
    confidence: number;
  }>;
}