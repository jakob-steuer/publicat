import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ItemCard } from '../components/ItemCard'
import { FilterBar } from '../components/FilterBar'
import type { Item, SyncProgress, Follow } from '../types'

const fetchTopics = async () => {
  const { data } = await axios.get('http://localhost:8001/topics/')
  return data
}

const fetchDashboard = async (topicId?: string, authorId?: string, showAcknowledged: boolean = false, showPreprints: boolean = true, showDiscarded: boolean = false, minScore: number = 0.20) => {
  let url = `http://localhost:8001/dashboard/?show_acknowledged=${showAcknowledged}&show_preprints=${showPreprints}&show_discarded=${showDiscarded}&min_score=${minScore}`
  if (topicId) url += `&topic_id=${topicId}`
  if (authorId) url += `&author_id=${encodeURIComponent(authorId)}`
  const { data } = await axios.get(url)
  return data
}

export default function Feed({ showRead, showPreprints, showDiscarded, searchQuery, minScore, isDark, toggleTheme }: any) {
  const queryClient = useQueryClient()
  const { topicId, authorId } = useParams()
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({})
  const [selectedItems, setSelectedItems] = useState<string[]>([])

  const { data: topics } = useQuery({ queryKey: ['topics'], queryFn: fetchTopics })
  
  const { data: follows } = useQuery({
    queryKey: ['follows'],
    queryFn: async () => {
      const { data } = await axios.get('http://localhost:8001/follows/')
      return data
    }
  })
  
  const { data: syncProgress } = useQuery<SyncProgress>({
    queryKey: ['syncProgress'],
    queryFn: async () => {
      const { data } = await axios.get('http://localhost:8001/items/progress')
      return data
    },
    refetchInterval: (query: { state: { data?: SyncProgress } }) => (query.state.data?.status === 'running' ? 1000 : false)
  })


  const { data: dashboard, isLoading, refetch } = useQuery({ 
    queryKey: ['dashboard', topicId, authorId, showRead, showPreprints, showDiscarded, minScore], 
    queryFn: () => fetchDashboard(topicId, authorId, showRead, showPreprints, showDiscarded, minScore) 
  })

  // Invalidate queries when sync completes
  useEffect(() => {
    if (syncProgress?.status === 'idle') {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    }
  }, [syncProgress?.status, queryClient])

  const acknowledgeItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`http://localhost:8001/items/${itemId}/acknowledge`)
    },
    onSuccess: () => refetch()
  })

  const unacknowledgeItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`http://localhost:8001/items/${itemId}/unacknowledge`)
    },
    onSuccess: () => refetch()
  })

  const starItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`http://localhost:8001/items/${itemId}/star`)
    },
    onSuccess: () => refetch()
  })

  const unstarItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`http://localhost:8001/items/${itemId}/unstar`)
    },
    onSuccess: () => refetch()
  })

  const hideItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`http://localhost:8001/items/${itemId}/hide`)
    },
    onSuccess: () => refetch()
  })

  const createFollow = useMutation({
    mutationFn: async (newFollow: Omit<Follow, 'id' | 'display_name'>) => {
      return axios.post('http://localhost:8001/follows/', newFollow)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['follows'] })
  })

  const deleteFollow = useMutation({
    mutationFn: async (followId: string) => {
      return axios.delete(`http://localhost:8001/follows/${followId}`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['follows'] })
  })

  const voteItem = useMutation({
    mutationFn: async ({ id, vote }: { id: string, vote: number }) => {
      return axios.post(`http://localhost:8001/items/${id}/vote`, { topic_id: topicId || null, vote })
    },
    onSuccess: () => refetch()
  })



  const handleSyncControl = async (action: 'pause' | 'resume' | 'abort') => {
    try {
      await axios.post('http://localhost:8001/items/sync/control', { action })
      queryClient.invalidateQueries({ queryKey: ['syncProgress'] })
    } catch (e) {
      console.error("Sync control failed", e)
    }
  }

  const toggleSelect = (itemId: string) => {
    setSelectedItems(prev => prev.includes(itemId) ? prev.filter(i => i !== itemId) : [...prev, itemId])
  }

  const handleExportBibtex = async (itemIds: string[]) => {
    try {
      const res = await axios.post('http://localhost:8001/api/export/bibtex', { item_ids: itemIds }, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'publikater_export.bib')
      document.body.appendChild(link)
      link.click()
      link.parentNode?.removeChild(link)
      setSelectedItems([]) // Clear selection after export
    } catch (e) {
      console.error("Export failed", e)
    }
  }

  const handleBulkRead = async () => {
    try {
      await Promise.all(selectedItems.map(id => axios.put(`http://localhost:8001/items/${id}/acknowledge`)))
      setSelectedItems([])
      refetch()
    } catch (e) {
      console.error("Bulk read failed", e)
    }
  }

  const handleBulkDismiss = async () => {
    try {
      await Promise.all(selectedItems.map(id => axios.put(`http://localhost:8001/items/${id}/hide`)))
      setSelectedItems([])
      refetch()
    } catch (e) {
      console.error("Bulk dismiss failed", e)
    }
  }

  const renderItemCard = (item: Item) => (
    <ItemCard 
      key={item.id}
      item={item}
      selectedItems={selectedItems}
      toggleSelect={toggleSelect}
      follows={follows}
      createFollow={createFollow}
      deleteFollow={deleteFollow}
      starItem={starItem}
      unstarItem={unstarItem}
      acknowledgeItem={acknowledgeItem}
      unacknowledgeItem={unacknowledgeItem}
      hideItem={hideItem}
      voteItem={voteItem}
    />
  )

  const renderSection = (title: string, icon: string, items: Item[], id: string) => {
    if (!items || items.length === 0) return null
    
    // Filter by search query if present
    const filteredItems = searchQuery.trim() 
      ? items.filter((item: Item) => 
          item.title?.toLowerCase().includes(searchQuery.toLowerCase()) || 
          item.abstract?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.authors?.some((a: string) => a.toLowerCase().includes(searchQuery.toLowerCase()))
        )
      : items

    if (filteredItems.length === 0) return null

    const isExpanded = expandedSections[title] || false
    const displayedItems = isExpanded || searchQuery.trim() ? filteredItems : filteredItems.slice(0, 6)
    
    return (
      <div id={id} className="mb-12 scroll-mt-24">
        <div className="flex justify-between items-end mb-4">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-bold flex items-center gap-2">{icon} {title}</h2>
            <button 
              onClick={() => {
                const allIds = displayedItems.map((i: Item) => i.id)
                const allSelected = allIds.every((id: string) => selectedItems.includes(id))
                if (allSelected) {
                  setSelectedItems(prev => prev.filter(id => !allIds.includes(id)))
                } else {
                  setSelectedItems(prev => Array.from(new Set([...prev, ...allIds])))
                }
              }}
              className="text-xs bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground px-2 py-1 rounded-md transition-colors"
            >
              Select All
            </button>
          </div>
          {items.length > 6 && (
            <button 
              onClick={() => setExpandedSections(prev => ({...prev, [title]: !isExpanded}))}
              className="text-sm text-primary hover:underline"
            >
              {isExpanded ? "Show less" : `View all (${items.length})`}
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayedItems.map(renderItemCard)}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 pb-20 pt-0 space-y-4">
      <FilterBar 
        topicId={topicId}
        authorId={authorId}
        follows={follows}
        topics={topics}
        dashboard={dashboard}
        syncProgress={syncProgress}
        handleSyncControl={handleSyncControl}
        isDark={isDark}
        toggleTheme={toggleTheme}
      />

      {isLoading ? (
        <div className="py-20 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading dashboard...</p>
        </div>
      ) : dashboard ? (
        <div className="space-y-12">
          {topics?.length === 0 ? (
            <div className="py-20 px-4 text-center border-2 border-dashed rounded-xl bg-card">
              <h3 className="text-2xl font-bold mb-4">Welcome to Publicat! 👋</h3>
              <p className="text-muted-foreground mb-4 max-w-md mx-auto">
                You don't have any topics set up yet. Publicat needs to know what you're interested in before it can fetch and summarize papers for you.
              </p>
              <div className="bg-background border border-foreground rounded-lg p-4 mb-6 max-w-md mx-auto text-left">
                <p className="text-sm text-foreground">
                  <span className="font-bold">Highly Recommended:</span> Before creating a topic, please add a free Semantic Scholar API key in the Settings page. Without it, the app will likely hit aggressive rate limits and fail to fetch papers.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link 
                  to="/settings" 
                  className="bg-primary text-primary-foreground hover:bg-primary/90 px-6 py-2.5 rounded-lg font-medium transition-colors"
                >
                  Create Your First Topic
                </Link>
                <Link 
                  to="/help" 
                  className="bg-muted text-muted-foreground hover:text-foreground px-6 py-2.5 rounded-lg font-medium transition-colors"
                >
                  Read the Guide
                </Link>
              </div>
            </div>
          ) : dashboard?.do_not_miss?.length === 0 && dashboard?.this_week?.length === 0 && dashboard?.starred?.length === 0 && dashboard?.highlighted_authors?.length === 0 ? (
            <div className="py-20 text-center border-2 border-dashed rounded-xl">
              <h3 className="text-xl font-semibold mb-2">Inbox Zero! 🎉</h3>
              <p className="text-muted-foreground">You are completely caught up on your research.</p>
            </div>
          ) : null}
          
          {renderSection("Do Not Miss", "", dashboard?.do_not_miss, "donotmiss")}
          {renderSection("Followed Authors", "", dashboard?.highlighted_authors, "highlighted")}
          {renderSection("Extracted Tools", "", dashboard?.tools, "tools")}
          {renderSection("This Week", "", dashboard?.this_week, "thisweek")}
          {renderSection("This Month", "", dashboard?.this_month, "thismonth")}
          {renderSection("Starred", "", dashboard?.starred, "starred")}

          {/* Fallback for unhandled sections */}
          {dashboard?.feed_sections && Object.entries(dashboard.feed_sections).map(([title, items]) => 
            renderSection(title, "", items as Item[], `section-${title}`)
          )}

          {selectedItems.length > 0 && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-foreground text-background px-6 py-3 rounded-full shadow-2xl flex items-center gap-4 z-50 animate-in slide-in-from-bottom-5">
              <span className="font-semibold text-sm">{selectedItems.length} selected</span>
              <div className="h-4 w-px bg-background/30"></div>
              <button 
                onClick={() => handleExportBibtex(selectedItems)}
                className="text-sm font-semibold hover:text-primary transition-colors flex items-center gap-2"
              >
                BibTeX 📥
              </button>
              <div className="h-4 w-px bg-background/30"></div>
              <button 
                onClick={handleBulkRead}
                className="text-sm font-semibold hover:text-green-400 transition-colors flex items-center gap-2"
              >
                Mark Read ✓
              </button>
              <div className="h-4 w-px bg-background/30"></div>
              <button 
                onClick={handleBulkDismiss}
                className="text-sm font-semibold hover:text-red-400 transition-colors flex items-center gap-2"
              >
                Dismiss ❌
              </button>
              <div className="h-4 w-px bg-background/30"></div>
              <button onClick={() => setSelectedItems([])} className="text-sm opacity-80 hover:opacity-100">
                Cancel
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
