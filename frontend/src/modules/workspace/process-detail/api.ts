import { apiClient } from '@shared/api/client';
import { getProcessGraph, updateProcessReport } from '@modules/workspace/processes/api';
import type { ProcessDetailDto } from '@modules/workspace/process-detail/contracts';

export async function getProcessDetail(processId: number) {
  return apiClient.get<ProcessDetailDto>(`/api/processes/${processId}`);
}

export { getProcessGraph, updateProcessReport };
