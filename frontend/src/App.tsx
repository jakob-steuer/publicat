import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Sun, Moon, Menu, X } from 'lucide-react'
import { api } from './lib/client'
import { usePrefs, type Prefs } from './hooks/usePrefs'
import { ToastProvider } from './components/ui/Toast'
import { useToast } from './hooks/useToast'
import { useSyncProgress } from './hooks/useSyncProgress'
import { SyncBar } from './components/triage/SyncBar'
import Inbox from './pages/Inbox'
import Library from './pages/Library'
import Settings from './pages/Settings'
import Disclaimer from './pages/Disclaimer'
import Help from './pages/Help'
import type { Topic } from './types'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } })

function timeAgo(iso: string, now: number): string {
  const mins = Math.round((now - new Date(iso).getTime()) / 60000)
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} h ago`
  return `${Math.round(hrs / 24)} d ago`
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${isActive ? 'bg-primary text-primary-foreground font-medium' : 'hover:bg-muted/60 text-foreground/80 hover:text-foreground'}`

function Badge({ n, active }: { n?: number; active?: boolean }) {
  if (!n) return null
  return <span className={`text-[10px] font-semibold tabular-nums px-1.5 py-px rounded-full ${active ? 'bg-primary-foreground/20' : 'bg-muted text-muted-foreground'}`}>{n}</span>
}

function Sidebar({ prefs, update, isMobileOpen, onClose }: { prefs: Prefs; update: (p: Partial<Prefs>) => void; isMobileOpen: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { data: topics = [] } = useQuery({ queryKey: ['topics'], queryFn: api.topics })
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const { data: sync } = useSyncProgress()
  const countParams = { min_score: prefs.minScore, days: prefs.days, show_preprints: prefs.showPreprints }
  const { data: counts } = useQuery({ queryKey: ['inboxCounts', countParams], queryFn: () => api.inboxCounts(countParams), refetchInterval: 60_000 })
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])
  const busy = sync?.status === 'running' || sync?.status === 'paused'
  const stopping = sync?.status === 'aborted'

  const startFetch = async () => {
    if (busy) return
    const { data } = await api.startFetch()
    if (data?.status === 'error') {
      toast(data.message ?? 'A job is already running', { kind: 'error' })
    } else {
      // show the bar immediately; the poll takes over from here
      qc.setQueryData(['syncProgress'], { status: 'running', message: data?.message ?? 'Starting fetch…', progress: 0, job: 'manual fetch' })
      toast(data?.message ?? 'Fetching new papers in the background', { kind: 'info' })
    }
    qc.invalidateQueries({ queryKey: ['syncProgress'] })
  }

  return (
    <>
      {isMobileOpen && <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-30 md:hidden" onClick={onClose} />}
      <aside className={`w-64 shrink-0 border-r border-border h-screen bg-card/95 flex flex-col overflow-y-auto fixed inset-y-0 left-0 z-40 transition-transform duration-300 md:sticky md:top-0 md:translate-x-0 ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="px-5 pt-5 pb-4 flex items-center gap-3">
          <img src="/logo.png" alt="" className="h-12 w-auto" />
          <div className="flex-1">
            <h1 className="text-xl font-bold tracking-tight text-primary leading-none">PUBLICAT</h1>
            <p className="text-[10px] text-muted-foreground mt-1 tracking-wide uppercase font-semibold">AI research feed</p>
          </div>
          <button onClick={onClose} className="md:hidden p-1 text-muted-foreground" aria-label="Close menu"><X size={18} /></button>
        </div>

        <div className="px-4 mb-4">
          <button onClick={startFetch} disabled={busy} className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-9 rounded-md font-medium text-sm disabled:opacity-50 transition-transform active:scale-95">
            {busy ? 'Syncing…' : stopping ? 'Fetch (after current job stops)' : 'Fetch latest papers'}
          </button>
          <div className="text-[10px] text-center mt-1.5 text-muted-foreground">{settings?.last_synced_at ? `Last fetched ${timeAgo(settings.last_synced_at, now)}` : 'Never fetched'}</div>
        </div>

        <nav className="px-3 space-y-0.5">
          <NavLink to="/" end onClick={onClose} className={navClass}>{({ isActive }) => <><span>All topics</span><Badge n={counts?.all} active={isActive} /></>}</NavLink>
          {topics.map((t: Topic) => (
            <NavLink key={t.id} to={`/topic/${t.id}`} onClick={onClose} className={navClass}>
              {({ isActive }) => <><span className="truncate">{t.name}</span><Badge n={counts?.topics[t.id]} active={isActive} /></>}
            </NavLink>
          ))}
        </nav>

        <nav className="px-3 mt-4 space-y-0.5">
          <NavLink to="/starred" onClick={onClose} className={navClass}>Starred library</NavLink>
          <NavLink to="/discarded" onClick={onClose} className={navClass}>Discarded</NavLink>
          <NavLink to="/settings" onClick={onClose} className={navClass}>Settings</NavLink>
        </nav>

        <div className="px-4 mt-5 space-y-3">
          <h2 className="px-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Triage options</h2>
          <label className="flex flex-col gap-1 text-sm px-1">
            <span className="flex justify-between"><span>Minimum relevance</span><span className="text-primary font-medium tabular-nums">{Math.round(prefs.minScore * 100)}%</span></span>
            <input type="range" min="0" max="0.95" step="0.05" value={prefs.minScore} onChange={e => update({ minScore: parseFloat(e.target.value) })} className="accent-primary" />
          </label>
          <label className="flex items-center gap-2 text-sm px-1 cursor-pointer"><input type="checkbox" checked={prefs.showPreprints} onChange={e => update({ showPreprints: e.target.checked })} className="accent-primary" /> Show preprints</label>
          <label className="flex items-center gap-2 text-sm px-1 cursor-pointer"><input type="checkbox" checked={prefs.showRated} onChange={e => update({ showRated: e.target.checked })} className="accent-primary" /> Show rated papers</label>
          <label className="flex items-center gap-2 text-sm px-1 cursor-pointer"><input type="checkbox" checked={prefs.autoAdvance} onChange={e => update({ autoAdvance: e.target.checked })} className="accent-primary" /> Advance after voting</label>
          <label className="flex items-center gap-2 text-sm px-1 cursor-pointer" title="Three papers a day from just below your threshold, so the ranker can be corrected when your interests shift"><input type="checkbox" checked={prefs.wildcards} onChange={e => update({ wildcards: e.target.checked })} className="accent-primary" /> Daily wildcards</label>
          <label className="flex items-center justify-between gap-2 text-sm px-1">
            <span>Look back</span>
            <select value={prefs.days} onChange={e => update({ days: parseInt(e.target.value, 10) })} className="bg-background border border-border rounded px-1 py-0.5 text-xs">
              <option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={56}>8 weeks</option><option value={0}>everything</option>
            </select>
          </label>
        </div>

        <div className="mt-auto px-5 py-5 space-y-2 text-[12px]">
          <button onClick={() => update({ dark: !prefs.dark })} className="flex items-center gap-2 text-muted-foreground hover:text-primary">{prefs.dark ? <Sun size={14} /> : <Moon size={14} />} {prefs.dark ? 'Light mode' : 'Dark mode'}</button>
          <NavLink to="/help" onClick={onClose} className="block text-muted-foreground hover:text-primary">Help &amp; shortcuts</NavLink>
          <NavLink to="/disclaimer" onClick={onClose} className="block text-muted-foreground hover:text-primary">Impressum &amp; disclaimer</NavLink>
          <a href="https://www.semanticscholar.org" target="_blank" rel="noopener noreferrer" className="block text-muted-foreground/60 hover:text-primary pt-2">Powered by Semantic Scholar ↗</a>
        </div>
      </aside>
    </>
  )
}

function Shell() {
  const { prefs, update } = usePrefs()
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="h-screen bg-background flex flex-col md:flex-row overflow-hidden">
      <div className="md:hidden flex items-center p-3 border-b bg-card shrink-0">
        <button onClick={() => setMenuOpen(true)} className="p-2 mr-2 rounded-md bg-muted/50" aria-label="Open menu"><Menu size={18} /></button>
        <span className="font-bold tracking-tight">PUBLICAT</span>
      </div>
      <Sidebar prefs={prefs} update={update} isMobileOpen={menuOpen} onClose={() => setMenuOpen(false)} />
      <main className="flex-1 min-w-0 min-h-0 h-full overflow-hidden flex flex-col">
        <SyncBar />
        <div className="flex-1 min-h-0">
        <Routes>
          <Route path="/" element={<Inbox prefs={prefs} updatePrefs={update} />} />
          <Route path="/topic/:topicId" element={<Inbox prefs={prefs} updatePrefs={update} />} />
          <Route path="/author/:authorId" element={<Inbox prefs={prefs} updatePrefs={update} />} />
          <Route path="/starred" element={<Library mode="starred" prefs={prefs} />} />
          <Route path="/discarded" element={<Library mode="discarded" prefs={prefs} />} />
          <Route path="/settings" element={<div className="h-full overflow-y-auto"><Settings /></div>} />
          <Route path="/disclaimer" element={<div className="h-full overflow-y-auto"><Disclaimer /></div>} />
          <Route path="/help" element={<div className="h-full overflow-y-auto"><Help /></div>} />
        </Routes>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
