import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BookMarked, ChevronRight } from 'lucide-react'
import { api, errorMessage } from '../lib/client'
import { useToast } from '../hooks/useToast'
import type { TopicDraft, ZoteroCollection } from '../types'

interface Props {
  /** Receives a topic draft built from the chosen collection; the caller shows it for editing. */
  onDraft: (draft: TopicDraft) => void;
}

/**
 * "Start from Zotero": pick a collection (or the whole library) and get a topic
 * draft whose seed papers are that collection's papers. The draft is only a
 * starting point; name, description and keywords stay editable before creating.
 */
export function ZoteroImport({ onDraft }: Props) {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const { data: status } = useQuery({ queryKey: ['zoteroLibraryStatus'], queryFn: api.zoteroLibraryStatus, enabled: open, retry: false })
  const { data: collections, isLoading, error } = useQuery<ZoteroCollection[]>({
    queryKey: ['zoteroCollections'],
    queryFn: api.zoteroCollections,
    enabled: open && !!status?.available,
    retry: false,
  })
  const preview = useMutation({
    mutationFn: (c: { key: string | null; name: string }) => api.zoteroPreview(c.key, c.name),
    onSuccess: p => {
      onDraft({
        name: p.name,
        description: p.description,
        keywords: p.suggested_keywords.join(', '),
        exclude_keywords: '',
        seed_papers: p.seed_papers,
        arxiv_categories: [],
      })
      const missed = p.unresolved_count ? ` ${p.unresolved_count} could not be matched (no DOI / arXiv id).` : ''
      toast(`${p.matched} of ${p.total_items} papers matched on Semantic Scholar.${missed} Review the draft below, then create the topic.`, { kind: 'success', duration: 8000 })
      setOpen(false)
    },
    onError: e => toast(errorMessage(e), { kind: 'error', duration: 8000 }),
  })

  const shown = (collections ?? []).filter(c => c.path.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="border border-border rounded-lg bg-muted/30">
      <button type="button" onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-2 px-4 py-3 text-left">
        <BookMarked size={16} className="text-red-600" />
        <span className="font-medium text-sm flex-1">Start from a Zotero collection</span>
        <span className="text-xs text-muted-foreground">its papers become the seed papers</span>
        <ChevronRight size={16} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>

      {open && (
        <div className="px-4 pb-4 text-sm space-y-3">
          {!status ? (
            <p className="text-muted-foreground">Looking for Zotero…</p>
          ) : !status.available ? (
            <div className="space-y-2 text-muted-foreground">
              <p className="text-foreground font-medium">Zotero is not reachable yet.</p>
              <p><strong>Desktop app:</strong> {status.local.message ?? 'not running'}</p>
              <p>In Zotero 7 open <em>Settings → Advanced</em> and tick <em>"Allow other applications on this computer to communicate with Zotero"</em>, then reopen this panel.</p>
              <p><strong>Without the desktop app:</strong> enter your Zotero user ID and a read-only API key under Settings → Zotero.</p>
            </div>
          ) : isLoading ? (
            <p className="text-muted-foreground">Loading collections…</p>
          ) : error ? (
            <p className="text-red-600">{errorMessage(error)}</p>
          ) : (
            <>
              <p className="text-muted-foreground">
                Each collection can become its own topic, so different research interests stay separate. Pick one; you can still rename it, rewrite the description and edit keywords before creating the topic. Repeat for further collections.
              </p>
              <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter collections…" className="w-full p-2 rounded border bg-background" />
              <div className="max-h-64 overflow-y-auto border border-border/60 rounded bg-background divide-y divide-border/60">
                <button type="button" disabled={preview.isPending} onClick={() => preview.mutate({ key: null, name: 'My Zotero library' })} className="w-full flex justify-between gap-3 px-3 py-2 text-left hover:bg-muted/60 disabled:opacity-50">
                  <span className="font-medium">Whole library</span>
                  <span className="text-xs text-muted-foreground">most recent 300 papers</span>
                </button>
                {shown.map(c => (
                  <button key={c.key} type="button" disabled={preview.isPending || c.num_items === 0} onClick={() => preview.mutate({ key: c.key, name: c.path })} className="w-full flex justify-between gap-3 px-3 py-2 text-left hover:bg-muted/60 disabled:opacity-50">
                    <span className="truncate">{c.path}</span>
                    <span className="text-xs text-muted-foreground tabular-nums shrink-0">{c.num_items} items</span>
                  </button>
                ))}
                {shown.length === 0 && <div className="px-3 py-2 text-muted-foreground">No collections match.</div>}
              </div>
              {preview.isPending && <p className="text-muted-foreground">Matching papers on Semantic Scholar… (a few seconds per 100 papers)</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
