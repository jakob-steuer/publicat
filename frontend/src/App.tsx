import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { Topic } from './types'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import axios from 'axios'
import Feed from './pages/Feed'
import Settings from './pages/Settings'
import Starred from './pages/Starred'
import Discarded from './pages/Discarded'
import Disclaimer from './pages/Disclaimer'
import Help from './pages/Help'

const queryClient = new QueryClient()

const fetchSyncProgress = async () => {
  const { data } = await axios.get('http://localhost:8001/items/progress')
  return data
}

const fetchSettings = async () => {
  const { data } = await axios.get('http://localhost:8001/settings/')
  return data
}

const fetchTopics = async () => {
  const { data } = await axios.get('http://localhost:8001/topics/')
  return data
}

function Sidebar({ isMobileOpen, onClose, showRated, setShowRated, showPreprints, setShowPreprints, searchQuery, setSearchQuery, minScore, setMinScore }: any) {
  const { data: topics } = useQuery({ queryKey: ['topics'], queryFn: fetchTopics })
  const { data: syncProgress } = useQuery({ queryKey: ['syncProgress'], queryFn: fetchSyncProgress, refetchInterval: (data: any) => (data?.status === 'running' || data?.status === 'paused') ? 2000 : false })
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })

  const handleFetch = async () => {
    if (syncProgress?.status === 'running' || syncProgress?.status === 'paused') return
    await axios.post('http://localhost:8001/items/fetch')
    queryClient.invalidateQueries({ queryKey: ['syncProgress'] })
  }

  function formatTimeAgo(isoString: string) {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffMins = Math.round(diffMs / 60000);
    if (diffMins < 60) return `${diffMins} mins ago`;
    const diffHrs = Math.round(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs} hours ago`;
    return `${Math.round(diffHrs / 24)} days ago`;
  }
  
  const baseClasses = "w-64 border-r border-border h-screen bg-card/95 flex flex-col overflow-y-auto"
  const mobileClasses = isMobileOpen 
    ? "fixed inset-y-0 left-0 z-40 transform translate-x-0 transition-transform duration-300 ease-in-out" 
    : "fixed inset-y-0 left-0 z-40 transform -translate-x-full transition-transform duration-300 ease-in-out"
  
  return (
    <>
      {/* Mobile backdrop */}
      {isMobileOpen && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-30 md:hidden" onClick={onClose} />
      )}
      
      <aside className={`md:sticky md:top-0 md:translate-x-0 ${baseClasses} ${mobileClasses}`}>
        <div className="px-6 mb-8 flex items-center justify-between gap-3 mt-6">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Publicat Logo" className="h-16 w-auto object-contain" />
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-primary leading-none">PUBLICAT</h1>
              <p className="text-[10px] text-muted-foreground mt-1 tracking-wide uppercase font-semibold">AI Research Feed</p>
            </div>
          </div>
          {isMobileOpen && (
            <button onClick={onClose} className="md:hidden p-2 text-muted-foreground hover:bg-muted rounded-full">
              ✕
            </button>
          )}
        </div>
        
        <div className="px-4 mb-6">
          <button 
            onClick={handleFetch}
            disabled={syncProgress?.status === 'running' || syncProgress?.status === 'paused'}
            className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-9 rounded-md font-medium shadow-sm transition-transform active:scale-95 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-1.5"
          >
            {syncProgress?.status === 'running' || syncProgress?.status === 'paused' ? '🔄 Syncing...' : 'Fetch Latest Papers'}
          </button>
          <div className="text-[10px] text-center mt-2 text-muted-foreground font-medium">
            {settings?.last_synced_at ? `Last fetched: ${formatTimeAgo(settings.last_synced_at)}` : 'Never fetched'}
          </div>
        </div>

        <div className="px-4 space-y-1 mb-8">
          <NavLink to="/" end onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-primary text-primary-foreground font-medium shadow-sm' : 'hover:bg-muted/50 text-foreground/80 hover:text-foreground'}`}>
            All Topics
          </NavLink>
          <NavLink to="/starred" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-primary text-primary-foreground font-medium shadow-sm' : 'hover:bg-muted/50 text-foreground/80 hover:text-foreground'}`}>
            Starred Library
          </NavLink>
          <NavLink to="/settings" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-primary text-primary-foreground font-medium shadow-sm' : 'hover:bg-muted/50 text-foreground/80 hover:text-foreground'}`}>
            Settings
          </NavLink>
        </div>

        <div className="px-4 space-y-1">
          <h2 className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Your Topics</h2>
          {topics?.map((topic: Topic) => (
            <NavLink key={topic.id} to={`/topic/${topic.id}`} onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted/50 text-foreground/80 hover:text-foreground'}`}>
              <span className="truncate">{topic.name}</span>
            </NavLink>
          ))}
        </div>

        <div className="px-4 space-y-3 mb-8 mt-6">
          <h2 className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Options</h2>
          <input 
            type="text" 
            placeholder="🔍 Search in feed..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-1.5 border border-border/50 rounded-md text-sm w-full bg-muted/30 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
          <label className="flex items-center gap-2 text-sm text-foreground/80 cursor-pointer px-1">
            <input 
              type="checkbox" 
              checked={showRated} 
              onChange={(e) => setShowRated(e.target.checked)}
              className="rounded accent-primary"
            />
            Show Rated
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground/80 cursor-pointer px-1">
            <input 
              type="checkbox" 
              checked={showPreprints} 
              onChange={(e) => setShowPreprints(e.target.checked)}
              className="rounded accent-primary"
            />
            Show Preprints
          </label>
          <label className="flex flex-col gap-1 text-sm text-foreground/80 px-1 mt-2">
            <span className="flex justify-between">
              <span>Minimum Score</span>
              <span className="text-primary font-medium">{minScore.toFixed(2)}</span>
            </span>
            <input 
              type="range" 
              min="0" 
              max="1" 
              step="0.05" 
              value={minScore} 
              onChange={(e) => setMinScore(parseFloat(e.target.value))}
              className="accent-primary"
            />
          </label>
        </div>

        <div className="mt-auto pb-6 px-6 space-y-4 pt-4">
          <div className="space-y-2">
            <NavLink to="/help" onClick={onClose} className={({ isActive }) => `text-[12px] hover:text-primary transition-colors flex items-center gap-2 ${isActive ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
              Help & Tutorial
            </NavLink>
            <NavLink to="/disclaimer" onClick={onClose} className={({ isActive }) => `text-[11px] hover:text-primary transition-colors flex items-center gap-2 ${isActive ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
              Impressum & Disclaimer
            </NavLink>
            <a href="https://www.semanticscholar.org" target="_blank" rel="noopener noreferrer" className="mt-6 text-[10px] text-muted-foreground/60 hover:text-primary transition-colors flex items-center gap-2">
              Powered by Semantic Scholar ↗
            </a>
          </div>
        </div>
      </aside>
    </>
  )
}

function Layout({ children, showRated, setShowRated, showPreprints, setShowPreprints, searchQuery, setSearchQuery, minScore, setMinScore }: any) {
  const [isMobileOpen, setIsMobileOpen] = useState(false)

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      {/* Mobile Topbar */}
      <div className="md:hidden flex items-center p-4 border-b bg-card sticky top-0 z-30">
        <button onClick={() => setIsMobileOpen(true)} className="p-2 mr-3 bg-muted/50 rounded-md">
          ☰
        </button>
        <span className="font-bold tracking-tight">PUBLIKATER</span>
      </div>

      <Sidebar isMobileOpen={isMobileOpen} onClose={() => setIsMobileOpen(false)} showRated={showRated} setShowRated={setShowRated} showPreprints={showPreprints} setShowPreprints={setShowPreprints} searchQuery={searchQuery} setSearchQuery={setSearchQuery} minScore={minScore} setMinScore={setMinScore} />
      
      <main className="flex-1 min-w-0 md:h-screen md:overflow-y-auto relative">
        {children}
      </main>
    </div>
  )
}

function App() {
  const [showRated, setShowRated] = useState(() => {
    const saved = localStorage.getItem('publikater_show_rated')
    return saved !== null ? saved === 'true' : false
  })
  const [showPreprints, setShowPreprints] = useState(() => {
    const saved = localStorage.getItem('publikater_show_preprints')
    return saved !== null ? saved === 'true' : true
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [minScore, setMinScore] = useState(0.20)
  const [isDark, setIsDark] = useState(() => {
    const savedTheme = localStorage.getItem('theme')
    if (savedTheme) return savedTheme === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    localStorage.setItem('publikater_show_rated', showRated.toString())
  }, [showRated])

  useEffect(() => {
    localStorage.setItem('publikater_show_preprints', showPreprints.toString())
  }, [showPreprints])

  const toggleTheme = () => {
    const nextDark = !isDark
    setIsDark(nextDark)
    if (nextDark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }

  // Initial load
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDark])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout showRated={showRated} setShowRated={setShowRated} showPreprints={showPreprints} setShowPreprints={setShowPreprints} searchQuery={searchQuery} setSearchQuery={setSearchQuery} minScore={minScore} setMinScore={setMinScore}>
          <Routes>
            <Route path="/" element={<Feed showRated={showRated} showPreprints={showPreprints} searchQuery={searchQuery} minScore={minScore} isDark={isDark} toggleTheme={toggleTheme} />} />
            <Route path="/topic/:topicId" element={<Feed showRated={showRated} showPreprints={showPreprints} searchQuery={searchQuery} minScore={minScore} isDark={isDark} toggleTheme={toggleTheme} />} />
            <Route path="/author/:authorId" element={<Feed showRated={showRated} showPreprints={showPreprints} searchQuery={searchQuery} minScore={minScore} isDark={isDark} toggleTheme={toggleTheme} />} />
            <Route path="/starred" element={<Starred />} />
            <Route path="/discarded" element={<Discarded />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/disclaimer" element={<Disclaimer />} />
            <Route path="/help" element={<Help />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

