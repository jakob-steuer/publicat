import type { Topic, Follow, SyncProgress, Dashboard } from '../types'
import { Sun, Moon } from 'lucide-react'

interface FilterBarProps {
  authorId?: string;
  topicId?: string;
  follows: Follow[];
  topics: Topic[];
  dashboard: Dashboard;
  syncProgress?: SyncProgress;
  handleSyncControl: (action: 'pause' | 'resume' | 'abort') => void;
  isDark: boolean;
  toggleTheme: () => void;
}

export function FilterBar({
  authorId,
  topicId,
  follows,
  topics,
  dashboard,
  syncProgress,
  handleSyncControl,
  isDark,
  toggleTheme
}: FilterBarProps) {

  return (
    <div className="sticky top-0 bg-background/95 backdrop-blur z-10 pt-2 pb-4 border-b mb-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1 mt-3">
            {authorId 
              ? `Author Dashboard: ${follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value === authorId)?.display_name || authorId.replace("AUTHOR_ID:", "").replace("ORCID:", "")}`
              : topicId 
                ? topics?.find((t: Topic) => t.id === topicId)?.name 
                : 'All Topics Feed'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {dashboard?.do_not_miss?.length || 0} top papers, {topics?.length || 0} active topics tracked.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end w-full md:w-auto gap-3">
          <button 
            onClick={() => {
              const url = topicId 
                ? `http://localhost:8001/api/export/zotero/rss?topic_id=${topicId}`
                : `http://localhost:8001/api/export/zotero/rss`
              navigator.clipboard.writeText(url)
              alert("Zotero RSS URL copied to clipboard! Add this as a New Feed in Zotero.")
            }}
            className="text-xs bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 px-3 py-1.5 rounded-md flex items-center gap-1.5 font-semibold transition-colors"
            title="Copy Zotero RSS Feed URL"
          >
            Zotero RSS URL
          </button>
          
          <button 
            onClick={toggleTheme}
            className="p-2 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Toggle Theme"
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
      
      {/* Sync Progress Bar */}
      {syncProgress?.status && (syncProgress.status === 'running' || syncProgress.status === 'paused') && (
        <div className="mb-4 bg-muted/50 border rounded-md p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium flex items-center gap-2">
              <span className="text-lg leading-none">{syncProgress.status === 'paused' ? '⏸' : '🔄'}</span> 
              <span className="leading-none pt-0.5">{syncProgress.message}</span>
            </span>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground font-bold">{syncProgress.progress}%</span>
              <div className="h-4 w-px bg-border"></div>
              {syncProgress.status === 'running' ? (
                <button onClick={() => handleSyncControl('pause')} className="text-xs font-semibold text-amber-600 hover:text-amber-700">Pause</button>
              ) : (
                <button onClick={() => handleSyncControl('resume')} className="text-xs font-semibold text-emerald-600 hover:text-emerald-700">Resume</button>
              )}
              <button onClick={() => handleSyncControl('abort')} className="text-xs font-semibold text-red-600 hover:text-red-700">Abort</button>
            </div>
          </div>
          <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-500 ease-out ${syncProgress.status === 'paused' ? 'bg-amber-500' : 'bg-primary'}`}
              style={{ width: `${syncProgress.progress}%` }}
            />
          </div>
          {(syncProgress.message.includes('Scoring') || syncProgress.progress < 90) && (
            <div className="mt-2 text-[10px] text-muted-foreground italic">
              (First-time initialization for a new topic may take a few minutes)
            </div>
          )}
        </div>
      )}

      {/* Local Sticky Nav & Search */}
      <div className="flex flex-col md:flex-row gap-4 justify-between items-center pb-2">
        <div className="flex gap-2 overflow-x-auto text-sm font-medium hide-scrollbar w-full md:w-auto">
          <a href="#donotmiss" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">Do Not Miss</a>
          <a href="#highlighted" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">Followed Authors</a>
          <a href="#tools" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">Tools</a>
          <a href="#thisweek" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">This Week</a>
          <a href="#thismonth" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">This Month</a>
          <a href="#starred" className="bg-muted/60 text-muted-foreground hover:bg-primary/10 hover:text-primary border border-transparent hover:border-primary/20 px-4 py-1.5 rounded-full transition-all whitespace-nowrap shadow-sm">Starred</a>
        </div>
      </div>
    </div>
  )
}
