import { useEffect, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { RefreshCw, Search } from 'lucide-react'
import { api } from '../lib/client'
import { absoluteApiUrl } from '../lib/api'
import type { InboxFilter, InboxParams, Item, Topic } from '../types'
import type { Prefs } from '../hooks/usePrefs'
import { PaperList } from '../components/triage/PaperList'
import { SyncBar } from '../components/triage/SyncBar'
import { useToast } from '../hooks/useToast'
import { Onboarding } from './Onboarding'

const PAGE = 50

const FILTERS: Array<{ id: InboxFilter; label: string }> = [
  { id: 'all', label: 'Inbox' },
  { id: 'top', label: 'Do not miss' },
  { id: 'week', label: 'This week' },
  { id: 'month', label: 'This month' },
  { id: 'authors', label: 'Followed authors' },
]

interface Props {
  prefs: Prefs;
  updatePrefs: (p: Partial<Prefs>) => void;
}

export default function Inbox({ prefs, updatePrefs }: Props) {
  const { topicId, authorId } = useParams()
  const { toast } = useToast()
  const [filter, setFilter] = useState<InboxFilter>('all')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const h = setTimeout(() => setQ(search.trim()), 350)
    return () => clearTimeout(h)
  }, [search])

  const { data: topics = [], isLoading: topicsLoading } = useQuery({ queryKey: ['topics'], queryFn: api.topics })
  const { data: follows = [] } = useQuery({ queryKey: ['follows'], queryFn: api.follows })

  const params: InboxParams = useMemo(() => ({
    topic_id: topicId,
    author_id: authorId,
    min_score: prefs.minScore,
    days: prefs.days,
    show_acknowledged: prefs.showRated,
    show_preprints: prefs.showPreprints,
    show_discarded: prefs.showRated,
    q: q || undefined,
    filter,
    sort: prefs.sort,
    limit: PAGE,
  }), [topicId, authorId, prefs.minScore, prefs.days, prefs.showRated, prefs.showPreprints, q, filter, prefs.sort])

  const query = useInfiniteQuery({
    queryKey: ['inbox', params],
    queryFn: ({ pageParam }) => api.inbox({ ...params, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: last => (last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: topics.length > 0,
  })

  const items: Item[] = useMemo(() => {
    const seen = new Set<string>()
    const out: Item[] = []
    for (const page of query.data?.pages ?? []) for (const it of page.items) if (!seen.has(it.id)) { seen.add(it.id); out.push(it) }
    return out
  }, [query.data])
  const total = query.data?.pages[0]?.total ?? 0

  const topic: Topic | undefined = topics.find(t => t.id === topicId)
  const authorName = authorId ? follows.find(f => f.entity_value === authorId)?.display_name ?? authorId.replace(/^(AUTHOR_ID|ORCID):/, '') : null
  const title = authorName ? `Papers by ${authorName}` : topic ? topic.name : 'All topics'

  if (!topicsLoading && topics.length === 0) return <Onboarding />

  const copyZoteroRss = () => {
    const url = absoluteApiUrl(topicId ? `/api/export/zotero/rss?topic_id=${topicId}` : '/api/export/zotero/rss')
    navigator.clipboard.writeText(url).then(() => toast('Zotero RSS URL copied. In Zotero: New Feed → From URL.', { kind: 'success' }))
  }

  const header = (
    <div className="border-b border-border bg-background/95 backdrop-blur sticky top-0 z-20">
      <SyncBar />
      <div className="px-3 pt-3 pb-2 flex flex-wrap items-end gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight truncate">{title}</h1>
          <p className="text-xs text-muted-foreground">
            {query.isLoading ? 'Loading…' : `${total} paper${total === 1 ? '' : 's'}${prefs.showRated ? '' : ' to triage'}`}
            {topic?.description ? ` · ${topic.description.slice(0, 90)}${topic.description.length > 90 ? '…' : ''}` : ''}
          </p>
        </div>
        <div className="flex-1" />
        <div className="relative">
          <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search title, abstract, authors…  ( / )"
            className="pl-7 pr-2 py-1.5 text-sm rounded-md border border-border bg-background w-64 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <select value={prefs.sort} onChange={e => updatePrefs({ sort: e.target.value as Prefs['sort'] })} className="text-sm border border-border rounded-md bg-background px-2 py-1.5" title="Sort">
          <option value="score">Best match first</option>
          <option value="date">Newest first</option>
        </select>
        <button onClick={() => query.refetch()} className="p-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground" title="Refresh list"><RefreshCw size={15} className={query.isFetching ? 'animate-spin' : ''} /></button>
        <button onClick={copyZoteroRss} className="text-xs px-2.5 py-1.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 font-semibold" title="Copy the Zotero RSS feed URL for this scope">Zotero RSS</button>
      </div>
      <div className="px-3 pb-2 flex gap-1.5 overflow-x-auto hide-scrollbar">
        {FILTERS.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)} className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap border transition-colors ${filter === f.id ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted/50 text-muted-foreground border-transparent hover:border-primary/30 hover:text-foreground'}`}>
            {f.label}
          </button>
        ))}
      </div>
    </div>
  )

  const emptyState = query.isLoading ? (
    <div className="py-20 text-center text-muted-foreground"><div className="inline-block h-7 w-7 animate-spin rounded-full border-4 border-primary border-r-transparent mb-3" /><p>Loading papers…</p></div>
  ) : query.isError ? (
    <div className="py-20 text-center text-red-600">Could not load the inbox. Is the backend running?</div>
  ) : q || filter !== 'all' ? (
    <div className="py-20 text-center text-muted-foreground">Nothing matches. <button className="text-primary hover:underline" onClick={() => { setSearch(''); setFilter('all') }}>Clear filters</button></div>
  ) : (
    <div className="py-20 px-6 text-center">
      <h3 className="text-xl font-semibold mb-2">Inbox zero 🎉</h3>
      <p className="text-muted-foreground text-sm max-w-md mx-auto">
        Nothing above {Math.round(prefs.minScore * 100)}% relevance from the last {prefs.days} days. Lower the minimum score in the sidebar, turn on "show rated", or <Link to="/settings" className="text-primary hover:underline">fetch new papers</Link>.
      </p>
    </div>
  )

  return (
    <div className="h-full min-h-0">
      <PaperList
        items={items}
        topics={topics}
        showTopic={!topicId}
        autoAdvance={prefs.autoAdvance}
        onReachEnd={() => { if (query.hasNextPage && !query.isFetchingNextPage) query.fetchNextPage() }}
        emptyState={emptyState}
        header={header}
        footer={
          query.hasNextPage ? (
            <div className="py-4 text-center">
              <button onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage} className="text-xs px-3 py-1.5 rounded-full bg-card border border-border shadow hover:bg-muted">
                {query.isFetchingNextPage ? 'Loading…' : `Load more (${total - items.length} left)`}
              </button>
            </div>
          ) : items.length > 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">End of list · {total} papers</div>
          ) : null
        }
        searchRef={searchRef}
      />
    </div>
  )
}
