import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/client'
import type { SyncProgress } from '../types'

export function useSyncProgress() {
  return useQuery<SyncProgress>({
    queryKey: ['syncProgress'],
    queryFn: api.progress,
    refetchInterval: q => {
      const s = q.state.data?.status
      return s === 'running' || s === 'paused' || s === 'aborted' ? 1500 : 5000
    },
  })
}
