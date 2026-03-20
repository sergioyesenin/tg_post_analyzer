import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getJobResult, getJobStatus } from '@shared/jobs/api';
import type { AcceptedJobResponse, JobResultResponse } from '@shared/jobs/contracts';

type AsyncJobActionConfig<TVariables> = {
  actionLabel: string;
  mutationFn: (variables: TVariables) => Promise<AcceptedJobResponse>;
  onInvalidate: () => Promise<unknown>;
};

export type AsyncJobTerminalState = {
  actionLabel: string;
  jobId: number;
  status: 'success' | 'failed';
  result: JobResultResponse | null;
};

function isTerminalJobStatus(status: string | undefined) {
  return status === 'done' || status === 'failed';
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

export function useAsyncJobAction<TVariables>({
  actionLabel,
  mutationFn,
  onInvalidate,
}: AsyncJobActionConfig<TVariables>) {
  const queryClient = useQueryClient();
  const [activeJob, setActiveJob] = useState<AcceptedJobResponse | null>(null);
  const [terminalState, setTerminalState] = useState<AsyncJobTerminalState | null>(null);

  const mutation = useMutation({
    mutationFn,
    onSuccess: (job) => {
      setActiveJob(job);
      setTerminalState(null);
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

  const currentStatus = useMemo(() => {
    if (mutation.isPending) {
      return 'pending';
    }

    return jobStatusQuery.data?.status ?? (terminalState?.status === 'success' ? 'done' : terminalState?.status ?? null);
  }, [jobStatusQuery.data?.status, mutation.isPending, terminalState?.status]);

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
      mutation.reset();
    },
  };
}
