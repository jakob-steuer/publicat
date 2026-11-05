import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { api } from '../lib/client'
import { absoluteApiUrl } from '../lib/api'
import type { Item } from '../types'
import type { Prefs } from '../hooks/usePrefs'
import { PaperList } from '../components/triage/PaperList'
import { useToast } from '../hooks/useToast'

interface Props {
  mode: 'starred' | 'discarded';
  prefs: Prefs;
}

/** Starred library and discarded papers share one list; only the data source differs. */
export default function Library({ mode, prefs }: Props) {
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [topicFilter, setTopicFilter] = useState<string>('all')
  const { data: items = [], isLoading } = useQuery({ queryKey: ['library', mode], queryFn: mode === 'starred' ? api.starred : api.discarded })
  const { data: topics = [] } = useQuery({ queryKey: ['topics'], queryFn: api.topics })

  // A paper sits under every topic it was tagged into (vote >= 1 there); without any
  // tag it sits under the topic that scored it best, else under "No topic".
  const topicsOf = (i: Item): string[] => {
    const tagged = (i.topic_votes ?? []).filter(v => (v.vote ?? 0) >= 1).map(v => v.topic_id)
    if (tagged.length) return tagged
    return i.topic_id ? [i.topic_id] : ['none']
  }
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const i of items) for (const t of topicsOf(i)) c[t] = (c[t] ?? 0) + 1
    return c
  }, [items])

  const filtered: Item[] = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items.filter(i => {
      if (topicFilter !== 'all' && !topicsOf(i).includes(topicFilter)) return false
      if (!q) return true
      return i.title?.toLowerCase().includes(q) || i.abstract?.toLowerCase().includes(q) || i.authors?.some(a => a.toLowerCase().includes(q))
    })
  }, [items, search, topicFilter])

  const chip = (id: string, label: string, n: number) => (
    <button key={id} onClick={() => setTopicFilter(id)} className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap border transition-colors ${topicFilter === id ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted/50 text-muted-foreground border-transparent hover:border-primary/30 hover:text-foreground'}`}>
      {label} <span className="tabular-nums opacity-70">{n}</span>
    </button>
  )

  const header = (
    <div className="border-b border-border bg-background/95 backdrop-blur sticky top-0 z-20">
    <div className="px-3 pt-3 pb-2 flex flex-wrap items-end gap-x-4 gap-y-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{mode === 'starred' ? 'Starred library' : 'Discarded papers'}</h1>
        <p className="text-xs text-muted-foreground">{items.length} papers{mode === 'discarded' ? ' · upvote or mark read to bring one back' : ' · kept forever, exported to Zotero RSS'}</p>
      </div>
      <div className="flex-1" />
      <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search saved papers…" className="px-2 py-1.5 text-sm rounded-md border border-border bg-background w-56" />
      {mode === 'starred' && (
        <>
          <a href={absoluteApiUrl('/api/export/bibtex/starred')} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border hover:bg-muted font-semibold"><Download size={13} /> All as BibTeX</a>
          <button
            onClick={() => navigator.clipboard.writeText(absoluteApiUrl('/api/export/zotero/rss')).then(() => toast('Zotero RSS URL copied', { kind: 'success' }))}
            className="text-xs px-2.5 py-1.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 font-semibold"
          >
            Zotero RSS
          </button>
        </>
      )}
    </div>
    <div className="px-3 pb-2 flex gap-1.5 overflow-x-auto hide-scrollbar">
      {chip('all', 'All', items.length)}
      {topics.filter(t => counts[t.id]).map(t => chip(t.id, t.name, counts[t.id]))}
      {counts['none'] ? chip('none', 'No topic', counts['none']) : null}
    </div>
    </div>
  )

  return (
    <div className="h-full min-h-0">
      <PaperList
        items={filtered}
        topics={topics}
        showTopic
        autoAdvance={prefs.autoAdvance}
        header={header}
        emptyState={
          <div className="py-20 text-center text-muted-foreground">
            {isLoading ? 'Loading…' : mode === 'starred' ? 'No starred papers yet. Press s on a paper to save it here.' : 'Nothing discarded.'}
          </div>
        }
      />
    </div>
  )
}
