export type AcceptedJobResponse = {
  status: 'queued';
  job_id: number;
  job_type: string;
  status_url: string;
  result_url: string;
};

export type JobStatusResponse = {
  id: number;
  type: string;
  status: string;
  priority: number;
  run_at: string;
  retry_at: string | null;
  attempts: number;
  max_attempts: number;
  locked_by: string | null;
  locked_at: string | null;
  heartbeat_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  result_url: string;
};

export type JobResultPendingResponse = {
  status: string;
  job_id: number;
  ready?: boolean;
  result?: unknown;
};

export type JobResultDoneResponse = Record<string, unknown>;

export type JobResultResponse = JobResultPendingResponse | JobResultDoneResponse;
