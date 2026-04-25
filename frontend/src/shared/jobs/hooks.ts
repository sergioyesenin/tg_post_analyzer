import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { tokenStorage } from '@shared/auth/token-storage';
import { getJobResult, getJobStatus } from '@shared/jobs/api';
import type { AcceptedJobResponse, JobResultResponse } from '@shared/jobs/contracts';

type ReportBuildEntityType = 'post' | 'event' | 'process';

type ReportBuildProgressConfig = {
  mode: 'report-build';
  entityType: ReportBuildEntityType;
  entityId: number | null;
};

type ReportBuildProgressEvent = {
  type: 'report_build_started' | 'report_build_completed' | 'report_build_failed' | 'report_build_blocked';
  entity_type: ReportBuildEntityType;
  entity_id: number;
  request_id: number;
  status: 'building_report' | 'completed' | 'failed' | 'blocked';
  timestamp: string;
  message?: string;
  result?: {
    report_id?: number;
    location?: string;
  };
  error?: {
    code?: string;
    message?: string;
  };
};

type AsyncJobActionConfig<TVariables> = {
  actionLabel: string;
  mutationFn: (variables: TVariables) => Promise<AsyncJobMutationResponse>;
  onInvalidate: () => Promise<unknown>;
  progress?: ReportBuildProgressConfig;
};

export type AsyncJobTerminalState = {
  actionLabel: string;
  jobId: number | null;
  status: 'success' | 'failed' | 'blocked';
  result: JobResultResponse | null;
};

type BlockedJobResponse = {
  status: 'blocked';
  reason?: string;
  message?: string;
};

type AsyncJobMutationResponse = AcceptedJobResponse | BlockedJobResponse | Record<string, unknown>;

function isTerminalJobStatus(status: string | undefined) {
  return status === 'done' || status === 'failed';
}

function isTerminalProgressStatus(status: ReportBuildProgressEvent['status'] | null | undefined) {
  return status === 'completed' || status === 'failed' || status === 'blocked';
}

function isAcceptedJobResponse(value: unknown): value is AcceptedJobResponse {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    candidate.status === 'queued' &&
    typeof candidate.job_id === 'number' &&
    typeof candidate.job_type === 'string' &&
    typeof candidate.status_url === 'string' &&
    typeof candidate.result_url === 'string'
  );
}

function isBlockedJobResponse(value: unknown): value is BlockedJobResponse {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return candidate.status === 'blocked';
}

export function summarizeJobResult(result: JobResultResponse | null) {
  if (!result) {
    return null;
  }

  if ('error' in result && typeof result.error === 'string') {
    return result.error;
  }

  const summaryKeys = ['status', 'report_id', 'post_id', 'channel_id', 'username', 'comments_saved', 'wait_seconds', 'job_id'];
  const parts = summaryKeys
    .map((key) => {
      const value = readSummaryValue(result, key);
      return value === undefined ? null : `${key}: ${String(value)}`;
    })
    .filter(Boolean);

  return parts.length > 0 ? parts.join(' · ') : JSON.stringify(result);
}

function readSummaryValue(result: JobResultResponse, key: string) {
  if (!(key in result)) {
    return undefined;
  }

  return (result as Record<string, unknown>)[key];
}

function isReportBuildProgressEvent(value: unknown): value is ReportBuildProgressEvent {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.type === 'string' &&
    typeof candidate.entity_type === 'string' &&
    typeof candidate.entity_id === 'number' &&
    typeof candidate.request_id === 'number' &&
    typeof candidate.status === 'string' &&
    typeof candidate.timestamp === 'string'
  );
}

function buildReportProgressWebSocketUrl({
  requestId,
  entityType,
  entityId,
  accessToken,
}: {
  requestId: number;
  entityType: ReportBuildEntityType;
  entityId: number;
  accessToken: string;
}) {
  const fallbackOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? fallbackOrigin;
  const url = new URL(baseUrl, fallbackOrigin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `${url.pathname.replace(/\/$/, '')}/api/reports/progress/ws`;
  url.searchParams.set('access_token', accessToken);
  url.searchParams.set('request_id', String(requestId));
  url.searchParams.set('entity_type', entityType);
  url.searchParams.set('entity_id', String(entityId));
  return url.toString();
}

export function useAsyncJobAction<TVariables>({
  actionLabel,
  mutationFn,
  onInvalidate,
  progress,
}: AsyncJobActionConfig<TVariables>) {
  const queryClient = useQueryClient();
  const [activeJob, setActiveJob] = useState<AcceptedJobResponse | null>(null);
  const [terminalState, setTerminalState] = useState<AsyncJobTerminalState | null>(null);
  const [progressEvent, setProgressEvent] = useState<ReportBuildProgressEvent | null>(null);
  const isReportBuildAction = progress?.mode === 'report-build' && progress.entityId !== null;

  const mutation = useMutation({
    mutationFn,
    onSuccess: (response) => {
      if (isAcceptedJobResponse(response)) {
        setActiveJob(response);
        setTerminalState(null);
        setProgressEvent(null);
        return;
      }

      setActiveJob(null);
      setProgressEvent(null);

      if (isBlockedJobResponse(response)) {
        const reason = typeof response.reason === 'string' && response.reason.trim() ? response.reason : 'blocked';
        const message =
          typeof response.message === 'string' && response.message.trim()
            ? response.message
            : 'Report build request was blocked.';
        setTerminalState({
          actionLabel,
          jobId: null,
          status: 'blocked',
          result: {
            status: 'blocked',
            reason,
            error: message,
          },
        });
      }
    },
  });

  const jobStatusQuery = useQuery({
    queryKey: ['jobs', activeJob?.job_id, 'status'],
    queryFn: () => getJobStatus(activeJob!.job_id),
    enabled: Boolean(activeJob?.job_id),
    retry: false,
    refetchInterval: (query) => (isTerminalJobStatus(query.state.data?.status) ? false : 1500),
  });

  const jobResultQuery = useQuery({
    queryKey: ['jobs', activeJob?.job_id, 'result'],
    queryFn: () => getJobResult(activeJob!.job_id),
    enabled: Boolean(activeJob?.job_id),
    retry: false,
    refetchInterval: () => (isTerminalJobStatus(jobStatusQuery.data?.status) ? false : 1500),
  });

  useEffect(() => {
    if (!activeJob || !jobStatusQuery.data || !isTerminalJobStatus(jobStatusQuery.data.status)) {
      return;
    }

    const result = jobResultQuery.data ?? null;
    const nextStatus = jobStatusQuery.data.status === 'done' ? 'success' : 'failed';
    const hasSameTerminalState =
      terminalState?.jobId === activeJob.job_id &&
      terminalState.status === nextStatus &&
      terminalState.actionLabel === actionLabel;

    if (hasSameTerminalState) {
      return;
    }

    setTerminalState({
      actionLabel,
      jobId: activeJob.job_id,
      status: nextStatus,
      result,
    });

    if (nextStatus === 'success') {
      void onInvalidate().then(() => {
        void queryClient.invalidateQueries({ queryKey: ['jobs', activeJob.job_id] });
      });
    }
  }, [actionLabel, activeJob, jobResultQuery.data, jobStatusQuery.data, onInvalidate, queryClient, terminalState]);

  useEffect(() => {
    if (!isReportBuildAction || !activeJob || typeof WebSocket === 'undefined') {
      return;
    }

    const reportBuildProgress = progress;
    if (!reportBuildProgress || reportBuildProgress.entityId === null) {
      return;
    }

    const accessToken = tokenStorage.load()?.accessToken;
    if (!accessToken) {
      return;
    }

    const socket = new WebSocket(
      buildReportProgressWebSocketUrl({
        requestId: activeJob.job_id,
        entityType: reportBuildProgress.entityType,
        entityId: reportBuildProgress.entityId,
        accessToken,
      }),
    );

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data));
        if (!isReportBuildProgressEvent(payload)) {
          return;
        }
        if (payload.request_id !== activeJob.job_id) {
          return;
        }
        setProgressEvent(payload);
      } catch {
        // Ignore malformed websocket payloads and keep polling fallback.
      }
    };

    return () => {
      socket.close();
    };
  }, [activeJob, isReportBuildAction, progress]);

  useEffect(() => {
    if (!activeJob || !progressEvent || !isTerminalProgressStatus(progressEvent.status)) {
      return;
    }

    const nextStatus =
      progressEvent.status === 'completed'
        ? 'success'
        : progressEvent.status === 'blocked'
          ? 'blocked'
          : 'failed';
    const nextResult =
      progressEvent.status === 'completed'
        ? ({
            status: 'completed',
            job_id: activeJob.job_id,
            ...(progressEvent.result?.report_id ? { report_id: progressEvent.result.report_id } : {}),
            ...(progressEvent.result?.location ? { location: progressEvent.result.location } : {}),
          } satisfies JobResultResponse)
        : ({
            status: progressEvent.status,
            job_id: activeJob.job_id,
            error: progressEvent.error?.message ?? progressEvent.message ?? 'Report build did not complete.',
          } satisfies JobResultResponse);

    const hasSameTerminalState =
      terminalState?.jobId === activeJob.job_id &&
      terminalState.status === nextStatus &&
      terminalState.actionLabel === actionLabel;
    if (hasSameTerminalState) {
      return;
    }

    setTerminalState({
      actionLabel,
      jobId: activeJob.job_id,
      status: nextStatus,
      result: nextResult,
    });

    if (nextStatus === 'success') {
      void onInvalidate().then(() => {
        void queryClient.invalidateQueries({ queryKey: ['jobs', activeJob.job_id] });
      });
    }
  }, [actionLabel, activeJob, onInvalidate, progressEvent, queryClient, terminalState]);

  const currentStatus = useMemo(() => {
    if (mutation.isPending) {
      return 'pending';
    }

    if (isReportBuildAction && activeJob) {
      if (progressEvent?.status) {
        return progressEvent.status;
      }
      if (jobStatusQuery.data?.status === 'done') {
        return 'completed';
      }
      if (jobStatusQuery.data?.status === 'failed') {
        return 'failed';
      }
      if (terminalState?.status === 'success') {
        return 'completed';
      }
      if (terminalState?.status === 'blocked') {
        return 'blocked';
      }
      if (terminalState?.status === 'failed') {
        return 'failed';
      }
      return 'building_report';
    }

    return jobStatusQuery.data?.status ?? (terminalState?.status === 'success' ? 'done' : terminalState?.status ?? null);
  }, [activeJob, isReportBuildAction, jobStatusQuery.data?.status, mutation.isPending, progressEvent?.status, terminalState?.status]);

  return {
    run: mutation.mutate,
    runAsync: mutation.mutateAsync,
    isSubmitting: mutation.isPending,
    mutationError: mutation.error,
    activeJob,
    jobStatus: currentStatus,
    jobStatusQuery,
    jobResultQuery,
    terminalState,
    resultSummary: summarizeJobResult(terminalState?.result ?? jobResultQuery.data ?? null),
    reset: () => {
      setActiveJob(null);
      setTerminalState(null);
      setProgressEvent(null);
      mutation.reset();
    },
  };
}
