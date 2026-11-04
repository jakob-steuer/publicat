import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, ThumbsUp, Minus, ThumbsDown, RefreshCw, BookMarked, Download } from 'lucide-react'
import { api, errorMessage } from '../../lib/client'
import { useToast } from '../../hooks/useToast'
import type { Vote } from '../../types'

interface Props {
  count: number;
  ids: string[];
  onVote: (v: Vote) => void;
  onClear: () => void;
  showVotes?: boolean;
}

export function BulkBar({ count, ids, onVote, onClear, showVotes = true }: Props) {
  const { toast } = useToast()
  const qc = useQueryClient()
  const rescore = useMutation({
    mutationFn: () => api.bulkRescore(ids),
    onSuccess: () => { toast(`Rescored ${ids.length} papers`, { kind: 'success' }); qc.invalidateQueries({ queryKey: ['inbox'] }); qc.invalidateQueries({ queryKey: ['library'] }); onClear() },
    onError: e => toast(errorMessage(e), { kind: 'error' }),
  })
  const zotero = useMutation({
    mutationFn: () => api.zoteroPush(ids),
    onSuccess: r => { toast(`Saved ${r.saved} papers to Zotero`, { kind: 'success' }); onClear() },
    onError: e => toast(errorMessage(e), { kind: 'error', duration: 6000 }),
  })
  if (count === 0) return null
  const btn = 'inline-flex items-center gap-1.5 text-sm font-semibold hover:text-primary transition-colors'
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-card border border-border shadow-2xl px-5 py-2.5 rounded-full flex items-center gap-4 z-50 animate-in slide-in-from-bottom-5">
      <span className="font-semibold text-sm tabular-nums">{count} selected</span>
      <div className="h-4 w-px bg-border" />
      {showVotes && (
        <>
          <div className="flex items-center gap-1.5">
            <button onClick={() => onVote(2)} className="w-8 h-8 rounded-full border border-border/60 flex items-center justify-center text-muted-foreground hover:text-yellow-500 hover:scale-110 transition-transform" title="Star all"><Star size={15} /></button>
            <button onClick={() => onVote(1)} className="w-8 h-8 rounded-full border border-border/60 flex items-center justify-center text-muted-foreground hover:text-green-500 hover:scale-110 transition-transform" title="Upvote all"><ThumbsUp size={15} /></button>
            <button onClick={() => onVote(0)} className="w-8 h-8 rounded-full border border-border/60 flex items-center justify-center text-muted-foreground hover:text-blue-500 hover:scale-110 transition-transform" title="Mark all read"><Minus size={15} /></button>
            <button onClick={() => onVote(-1)} className="w-8 h-8 rounded-full border border-border/60 flex items-center justify-center text-muted-foreground hover:text-red-500 hover:scale-110 transition-transform" title="Discard all"><ThumbsDown size={15} /></button>
          </div>
          <div className="h-4 w-px bg-border" />
        </>
      )}
      <button onClick={() => api.exportBibtex(ids).then(onClear)} className={btn} title="Download BibTeX"><Download size={15} /> BibTeX</button>
      <button onClick={() => zotero.mutate()} disabled={zotero.isPending} className={btn} title="Save into the running Zotero app"><BookMarked size={15} /> Zotero</button>
      <button onClick={() => rescore.mutate()} disabled={rescore.isPending} className={btn} title="Recompute scores"><RefreshCw size={15} className={rescore.isPending ? 'animate-spin' : ''} /> Rescore</button>
      <div className="h-4 w-px bg-border" />
      <button onClick={onClear} className="text-sm opacity-70 hover:opacity-100">Cancel</button>
    </div>
  )
}
