export type MonitorSeverity = 'ok' | 'warning' | 'critical' | 'degraded';

export type MonitorDependencyDto = {
  ok?: boolean;
  connected?: boolean;
  enabled?: boolean;
  status?: string;
  retention_mode?: string;
  last_heartbeat_at?: string | null;
  next_expected_run_at?: string | null;
  last_enqueue_at?: string | null;
  process_status?: string | null;
  latency_ms?: number | null;
  error?: string | null;
};

export type MonitorFullDto = {
  health: {
    status: string;
    time_utc: string;
    dependencies: Record<string, MonitorDependencyDto>;
  };
  system: {
    timestamp: string;
    host: {
      cpu_count: number | null;
      pid: number | null;
    };
    cpu: {
      system_percent: number | null;
      process_percent: number | null;
    };
    memory: {
      total_bytes: number | null;
      available_bytes: number | null;
      used_bytes: number | null;
      used_percent: number | null;
      process_rss_bytes: number | null;
    };
    disk: {
      total_bytes: number | null;
      used_bytes: number | null;
      free_bytes: number | null;
      used_percent: number | null;
    };
  };
  jobs: {
    total: number;
    by_status: Record<string, number>;
    pending_lag_seconds: number | null;
    retry_lag_seconds: number | null;
    dead_letter_count: number;
  };
  pipeline: {
    ingest: {
      last_ingested_at: string | null;
      ingest_lag_seconds: number | null;
      last_post_date: string | null;
      post_freshness_lag_seconds: number | null;
    };
    collect_comments: {
      window_since: string;
      error_pool_size: number;
      flood_count: number;
      rpc_count: number;
      flood_rate: number;
      rpc_rate: number;
    };
    backlog: {
      jobs_created_1h: number;
      jobs_done_1h: number;
      delta_1h: number;
    };
    archive: {
      retention_cutoff: string;
      oldest_unarchived_post_date: string | null;
      archive_lag_seconds: number | null;
      last_archive_job_at: string | null;
      archive_job_lag_seconds: number | null;
    };
    runtime: Record<
      string,
      {
        runtime: string;
        ok: boolean;
        status: string;
        process: {
          status: string;
          last_heartbeat_at: string | null;
          heartbeat_age_seconds: number | null;
          heartbeat_timeout_seconds: number | null;
          pid: number | null;
        };
      }
    >;
  };
  scheduler: {
    status: string;
    retention_mode: string;
    enabled: boolean;
    timezone: string;
    schedule: {
      retention_hour: number;
      retention_minute: number;
      last_expected_run_at: string;
      next_expected_run_at: string;
    };
    process: {
      status: string;
      last_heartbeat_at: string | null;
      heartbeat_age_seconds: number | null;
      heartbeat_timeout_seconds: number | null;
      pid: number | null;
    };
    last_archive_enqueue_at: string | null;
    last_jobs_retention_enqueue_at: string | null;
    last_enqueue_at: string | null;
    enqueue_lag_seconds: number | null;
  };
  alerts: {
    status: string;
    alerts_count: number;
    alerts: Array<{
      severity: string;
      metric: string;
      current: number | string | null;
      threshold: number | string | null;
      message: string;
    }>;
  };
  activity_24h: {
    since: string;
    posts_last_hours: number;
    comments_last_hours: number;
  };
  database: {
    database: string | null;
    bytes: number | null;
    pretty: string | null;
  };
};

export type JobsSummaryDto = {
  total: number;
  by_status: Record<string, number>;
};

export type PendingJobDto = {
  id: number;
  type: string;
  status: string;
  priority: number;
  run_at: string;
  retry_at: string | null;
  attempts: number;
  max_attempts: number;
  locked_by: string | null;
  last_error: string | null;
};

export type DeadLetterJobDto = {
  id: number;
  source_job_id: number | null;
  type: string;
  priority: number | null;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  failed_at: string;
};

export type RetryJobResponseDto = {
  status: string;
  dead_letter_id?: number;
  source_job_id?: number | null;
  new_job_id?: number | null;
  job_id?: number;
  type?: string;
  reason?: string;
};

export type JobsFilters = {
  limit: number;
};
