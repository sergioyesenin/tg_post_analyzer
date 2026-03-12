import { apiClient } from '@shared/api/client';
import type { JobResultResponse, JobStatusResponse } from '@shared/jobs/contracts';

export function getJobStatus(jobId: number) {
  return apiClient.get<JobStatusResponse>(`/api/jobs/${jobId}`);
}

export function getJobResult(jobId: number) {
  return apiClient.get<JobResultResponse>(`/api/jobs/${jobId}/result`);
}
