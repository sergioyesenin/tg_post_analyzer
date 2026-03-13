import { apiClient } from '@shared/api/client';
import type {
  DeadLetterJobDto,
  JobsFilters,
  JobsSummaryDto,
  MonitorFullDto,
  PendingJobDto,
  RetryJobResponseDto,
} from '@modules/platform/contracts';

function toQueryString(filters: JobsFilters) {
  const params = new URLSearchParams();
  params.set('limit', String(filters.limit));
  return params.toString();
}

export function getMonitorFull() {
  return apiClient.get<MonitorFullDto>('/api/monitor/full');
}

export function getJobsSummary() {
  return apiClient.get<JobsSummaryDto>('/api/jobs/summary');
}

export function getPendingJobs(filters: JobsFilters) {
  return apiClient.get<PendingJobDto[]>(`/api/jobs/pending?${toQueryString(filters)}`);
}

export function getDeadLetterJobs(filters: JobsFilters) {
  return apiClient.get<DeadLetterJobDto[]>(`/api/jobs/dead-letter?${toQueryString(filters)}`);
}

export function retryFailedJob(jobId: number) {
  return apiClient.post<RetryJobResponseDto>(`/api/jobs/failed/${jobId}/retry`);
}

export function retryDeadLetterJob(deadLetterId: number) {
  return apiClient.post<RetryJobResponseDto>(`/api/jobs/dead-letter/${deadLetterId}/retry`);
}
