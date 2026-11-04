import { useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Square } from 'lucide-react'
import { api } from '../../lib/client'
import { useSyncProgress } from '../../hooks/useSyncProgress'

/** Progress strip shown while a fetch runs, with pause / resume / abort. */
export function SyncBar() {
  const qc = useQueryClient()
  const { data } = useSyncProgress()
  if (!data || (data.status !== 'running' && data.status !== 'paused')) return null
  const control = async (action: 'pause' | 'resume' | 'abort') => {
    await api.syncControl(action)
    qc.invalidateQueries({ queryKey: ['syncProgress'] })
  }
  return (
    <div className="px-3 py-2 border-b border-border/60 bg-muted/30 text-xs">
      <div className="flex items-center gap-3">
        <span className="flex-1 truncate">{data.message}</span>
        <span className="font-bold tabular-nums">{data.progress}%</span>
        {data.status === 'running' ? (
          <button onClick={() => control('pause')} className="text-amber-600 hover:text-amber-700" title="Pause"><Pause size={13} /></button>
        ) : (
          <button onClick={() => control('resume')} className="text-emerald-600 hover:text-emerald-700" title="Resume"><Play size={13} /></button>
        )}
        <button onClick={() => control('abort')} className="text-red-600 hover:text-red-700" title="Abort"><Square size={13} /></button>
      </div>
      <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden mt-1.5">
        <div className={`h-full transition-all duration-500 ${data.status === 'paused' ? 'bg-amber-500' : 'bg-primary'}`} style={{ width: `${data.progress}%` }} />
      </div>
    </div>
  )
}
