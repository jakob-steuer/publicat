import { useEffect, useState } from 'react'
import axios from 'axios'
import type { PaperSearchResult, SeedPaper, TopicDraft } from '../types'

interface TopicFormProps {
  draft: TopicDraft;
  onChange: (next: TopicDraft) => void;
}

const ARXIV_SETS = ['cs', 'q-bio', 'physics', 'math', 'stat', 'eess', 'econ', 'q-fin']

/**
 * Shared fields for creating and editing a topic. Seed papers are looked up on
 * Semantic Scholar; their embeddings define the topic vector that every new
 * paper is compared to, which is far more precise than the description alone.
 */
export function TopicForm({ draft, onChange }: TopicFormProps) {
  const [seedQuery, setSeedQuery] = useState('')
  const [seedResults, setSeedResults] = useState<PaperSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [showAllSeeds, setShowAllSeeds] = useState(false)

  useEffect(() => {
    if (seedQuery.trim().length < 3) return
    const handle = setTimeout(async () => {
      setSearching(true)
      try {
        const { data } = await axios.get<PaperSearchResult[]>('/topics/search_papers', { params: { q: seedQuery.trim() } })
        setSeedResults(data)
      } catch {
        setSeedResults([])
      } finally {
        setSearching(false)
      }
    }, 450)
    return () => clearTimeout(handle)
  }, [seedQuery])

  const set = (patch: Partial<TopicDraft>) => onChange({ ...draft, ...patch })
  const addSeed = (p: PaperSearchResult) => {
    if (draft.seed_papers.some(s => s.paperId === p.paperId)) return
    const seed: SeedPaper = { paperId: p.paperId, title: p.title }
    set({ seed_papers: [...draft.seed_papers, seed] })
    setSeedQuery('')
    setSeedResults([])
  }
  const toggleCategory = (c: string) =>
    set({ arxiv_categories: draft.arxiv_categories.includes(c) ? draft.arxiv_categories.filter(x => x !== c) : [...draft.arxiv_categories, c] })

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Topic Name</label>
        <input type="text" value={draft.name} onChange={e => set({ name: e.target.value })} placeholder="e.g. Protein Design" className="w-full p-2 rounded border bg-background" required />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea value={draft.description} onChange={e => set({ description: e.target.value })} placeholder="What you want to track, focusing on methods and core concepts." className="w-full p-2 rounded border bg-background min-h-[90px]" required />
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Keywords <span className="text-muted-foreground font-normal">(boost)</span></label>
          <input type="text" value={draft.keywords} onChange={e => set({ keywords: e.target.value })} placeholder="CRISPR, Cas9, gene editing" className="w-full p-2 rounded border bg-background" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Exclude keywords <span className="text-muted-foreground font-normal">(hard filter)</span></label>
          <input type="text" value={draft.exclude_keywords} onChange={e => set({ exclude_keywords: e.target.value })} placeholder="mouse model, review" className="w-full p-2 rounded border bg-background" />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Seed papers <span className="text-muted-foreground font-normal">(define the topic by example)</span></label>
        <p className="text-xs text-muted-foreground mb-2">Pick 3 to 10 papers that are exactly what you want to see. New papers are compared to them; this works better than any description.</p>
        {draft.seed_papers.length > 0 && (
          <ul className="space-y-1 mb-2">
            {(showAllSeeds ? draft.seed_papers : draft.seed_papers.slice(0, 6)).map(s => (
              <li key={s.paperId} className="flex items-start gap-2 text-sm bg-muted/40 border border-border/50 rounded px-2 py-1">
                <span className="flex-1 leading-snug">{s.title || s.paperId}</span>
                <button type="button" onClick={() => set({ seed_papers: draft.seed_papers.filter(x => x.paperId !== s.paperId) })} className="text-muted-foreground hover:text-destructive" title="Remove seed paper">×</button>
              </li>
            ))}
            {draft.seed_papers.length > 6 && (
              <li>
                <button type="button" onClick={() => setShowAllSeeds(v => !v)} className="text-xs text-primary hover:underline">
                  {showAllSeeds ? 'Show fewer' : `Show all ${draft.seed_papers.length} seed papers`}
                </button>
              </li>
            )}
          </ul>
        )}
        <div className="relative">
          <input type="text" value={seedQuery} onChange={e => { setSeedQuery(e.target.value); if (e.target.value.trim().length < 3) setSeedResults([]) }} placeholder="Search Semantic Scholar by title…" className="w-full p-2 rounded border bg-background" />
          {(searching || seedResults.length > 0) && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-zinc-900 border rounded-md shadow-xl z-[100] max-h-72 overflow-y-auto">
              {searching && <div className="px-3 py-2 text-xs text-muted-foreground">Searching…</div>}
              {seedResults.map(r => (
                <button key={r.paperId} type="button" onClick={() => addSeed(r)} className="w-full text-left px-3 py-2 hover:bg-secondary border-b last:border-b-0 text-sm">
                  <div className="font-medium leading-snug">{r.title}</div>
                  <div className="text-xs text-muted-foreground">{[r.authors?.slice(0, 3).join(', '), r.venue, r.year].filter(Boolean).join(' · ')}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">arXiv categories to harvest <span className="text-muted-foreground font-normal">(none = cs + q-bio)</span></label>
        <div className="flex flex-wrap gap-1.5">
          {ARXIV_SETS.map(c => (
            <button key={c} type="button" onClick={() => toggleCategory(c)} className={`px-2 py-0.5 rounded-full text-xs border transition-colors ${draft.arxiv_categories.includes(c) ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted/40 text-muted-foreground border-border/50 hover:border-primary/40'}`}>
              {c}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
