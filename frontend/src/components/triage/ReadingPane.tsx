import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { ExternalLink, FileText, X, BookMarked } from 'lucide-react'
import type { Author, Item, Topic, Vote } from '../../types'
import { api, errorMessage } from '../../lib/client'
import { useFollows } from '../../hooks/useFollows'
import { useToast } from '../../hooks/useToast'
import { ReasonList, ScoreChip } from './ScoreChip'
import { TopicTags } from './TopicTags'
import { VoteButtons } from './VoteButtons'
import { formatDate } from '../../lib/format'

interface Props {
  item: Item;
  topics: Topic[];
  onClose: () => void;
  onVote: (v: Vote, topicId?: string | null) => void;
}

export function ReadingPane({ item, topics, onClose, onVote }: Props) {
  const { toast } = useToast()
  const { findFor, toggle } = useFollows()
  const [attributeTo, setAttributeTo] = useState<string>(item.topic_id ?? '')
  const { data: zotero } = useQuery({ queryKey: ['zoteroStatus'], queryFn: api.zoteroStatus, staleTime: 30_000, retry: false })
  const pushZotero = useMutation({
    mutationFn: () => api.zoteroPush([item.id]),
    onSuccess: () => toast('Saved to Zotero', { kind: 'success' }),
    onError: e => toast(errorMessage(e), { kind: 'error', duration: 6000 }),
  })

  const authors: Author[] = item.author_details ?? (item.authors ?? []).map(name => ({ name }))
  const summary = item.t3_summary || item.t2_summary
  const link = item.doi ? `https://doi.org/${item.doi}` : item.url
  const vote = (item.user_vote ?? undefined) as Vote | undefined

  return (
    <aside className="flex flex-col h-full bg-card border-l border-border" aria-label="Paper details">
      <div className="flex items-start gap-3 p-4 border-b border-border/60">
        {item.score !== undefined && item.score !== null && <ScoreChip score={item.score} reasons={item.reasons} size="md" />}
        <h2 className="flex-1 text-lg font-semibold leading-snug">{item.title}</h2>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1 -m-1" title="Close (Esc)" aria-label="Close"><X size={18} /></button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <VoteButtons value={vote} onVote={v => onVote(v, attributeTo || null)} size="md" />
          {topics.length > 1 && (
            <label className="flex items-center gap-1 text-xs text-muted-foreground ml-1">
              trains
              <select value={attributeTo} onChange={e => setAttributeTo(e.target.value)} className="bg-background border border-border rounded px-1 py-0.5 text-xs max-w-[18ch]">
                {!item.topic_id && <option value="">best topic</option>}
                {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          )}
          <div className="flex-1" />
          <button
            onClick={() => pushZotero.mutate()}
            disabled={pushZotero.isPending}
            title={zotero?.running ? 'Save into the running Zotero app' : 'Zotero desktop does not seem to be running'}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-semibold transition-colors ${zotero?.running ? 'border-red-300 text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/40' : 'border-border text-muted-foreground'}`}
          >
            <BookMarked size={14} /> {pushZotero.isPending ? 'Saving…' : 'Zotero'}
          </button>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          <a href={link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary/10 text-primary hover:bg-primary/20 font-semibold">
            <ExternalLink size={13} /> Read article
          </a>
          {item.is_open_access && item.open_access_pdf_url && (
            <a href={item.open_access_pdf_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-red-50 text-red-700 hover:bg-red-100 dark:bg-red-950/40 dark:text-red-300 font-semibold">
              <FileText size={13} /> PDF
            </a>
          )}
          {item.doi && <span className="px-2 py-1.5 text-muted-foreground font-mono">{item.doi}</span>}
        </div>

        <div className="text-xs text-muted-foreground space-y-0.5">
          <div>{[item.venue, formatDate(item.published_at)].filter(Boolean).join(' · ')}</div>
          {(item.citation_count ?? 0) > 0 && <div>{item.citation_count} citations{item.influential_citation_count ? ` · ${item.influential_citation_count} influential` : ''}</div>}
          {item.discovered_via && item.discovered_via.length > 0 && <div>Found via {item.discovered_via.join(', ')}</div>}
        </div>

        <div className="text-xs leading-relaxed flex flex-wrap gap-x-1.5 gap-y-1">
          {authors.map((a, i) => {
            const followed = !!findFor(a)
            const key = a.authorId ? `AUTHOR_ID:${a.authorId}` : a.orcid ? `ORCID:${a.orcid}` : null
            return (
              <span key={i} className="inline-flex items-center gap-0.5">
                {key ? <NavLink to={`/author/${key}`} className={`hover:underline ${followed ? 'text-primary font-semibold' : ''}`}>{a.name}</NavLink> : <span className={followed ? 'text-primary font-semibold' : ''}>{a.name}</span>}
                <button
                  onClick={() => toggle(a)}
                  title={followed ? 'Unfollow author' : 'Follow author'}
                  className={`w-3.5 h-3.5 rounded-full text-[9px] font-bold flex items-center justify-center ${followed ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-primary hover:text-primary-foreground'}`}
                >
                  {followed ? '✓' : '+'}
                </button>
                {i < authors.length - 1 && <span className="text-muted-foreground">,</span>}
              </span>
            )
          })}
        </div>

        <TopicTags item={item} topics={topics} />

        {(summary || item.t1_tldr) && (
          <section>
            <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">{summary ? 'AI summary' : 'TLDR (Semantic Scholar)'}</h3>
            <p className="font-serif leading-relaxed">{summary || item.t1_tldr}</p>
          </section>
        )}

        {item.tools && item.tools.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {item.tools.map((t, i) => <span key={i} className="px-2 py-0.5 bg-primary/10 text-primary rounded text-[11px] font-semibold border border-primary/20">{t}</span>)}
          </div>
        )}

        <section>
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">Abstract</h3>
          <p className="font-serif leading-relaxed whitespace-pre-line">{item.abstract}</p>
        </section>

        {item.reasons && item.reasons.length > 0 && (
          <section className="border-t border-border/60 pt-3">
            <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Why this score{item.topic_name ? ` for "${item.topic_name}"` : ''}</h3>
            <ReasonList reasons={item.reasons} />
          </section>
        )}
      </div>
    </aside>
  )
}
