import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useState } from 'react'
import { ItemCard } from '../components/ItemCard'
import type { Item, Follow } from '../types'
import { absoluteApiUrl } from '../lib/api'

const fetchDiscarded = async () => {
  const { data } = await axios.get('/items/discarded')
  return data
}

export default function Discarded() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedItems, setSelectedItems] = useState<string[]>([])
  const { data: items, isLoading, refetch } = useQuery({ 
    queryKey: ['discarded'], 
    queryFn: fetchDiscarded 
  })

  const { data: follows } = useQuery({
    queryKey: ['follows'],
    queryFn: async () => {
      const { data } = await axios.get('/follows/')
      return data
    }
  })

  const toggleSelect = (itemId: string) => {
    setSelectedItems(prev => prev.includes(itemId) ? prev.filter(i => i !== itemId) : [...prev, itemId])
  }

  const handleExportBibtex = async (itemIds: string[]) => {
    try {
      const res = await axios.post('/api/export/bibtex', { item_ids: itemIds }, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'publikater_export.bib')
      document.body.appendChild(link)
      link.click()
      link.parentNode?.removeChild(link)
      setSelectedItems([])
    } catch (e) {
      console.error("Export failed", e)
    }
  }

  const unstarItem = useMutation({
    mutationFn: async (itemId: string) => {
      return axios.put(`/items/${itemId}/unstar`)
    },
    onSuccess: () => refetch()
  })

  const createFollow = useMutation({
    mutationFn: async (newFollow: Omit<Follow, 'id' | 'display_name'>) => {
      return axios.post('/follows/', newFollow)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['follows'] })
  })

  const deleteFollow = useMutation({
    mutationFn: async (followId: string) => {
      return axios.delete(`/follows/${followId}`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['follows'] })
  })

  const starItem = useMutation({
    mutationFn: async (itemId: string) => axios.put(`/items/${itemId}/star`),
    onSuccess: () => refetch()
  })

  const acknowledgeItem = useMutation({
    mutationFn: async (itemId: string) => axios.put(`/items/${itemId}/acknowledge`),
    onSuccess: () => refetch()
  })

  const unacknowledgeItem = useMutation({
    mutationFn: async (itemId: string) => axios.put(`/items/${itemId}/unacknowledge`),
    onSuccess: () => refetch()
  })

  const hideItem = useMutation({
    mutationFn: async (itemId: string) => axios.put(`/items/${itemId}/hide`),
    onSuccess: () => refetch()
  })

  const unhideItem = useMutation({
    mutationFn: async (itemId: string) => axios.put(`/items/${itemId}/unhide`),
    onSuccess: () => refetch()
  })

  const filteredItems = items?.filter((item: Item) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return item.title?.toLowerCase().includes(q) || item.abstract?.toLowerCase().includes(q) || item.authors?.some(a => a.toLowerCase().includes(q))
  })

  const renderItemCard = (item: Item & { score?: number }) => (
    <ItemCard 
      key={item.id}
      item={item}
      selectedItems={selectedItems}
      toggleSelect={toggleSelect}
      follows={follows || []}
      createFollow={createFollow}
      deleteFollow={deleteFollow}
      starItem={starItem}
      unstarItem={unstarItem}
      acknowledgeItem={acknowledgeItem}
      unacknowledgeItem={unacknowledgeItem}
      hideItem={hideItem}
      unhideItem={unhideItem}
    />
  )

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4 pb-20">
      <div className="sticky top-0 bg-background/95 backdrop-blur z-10 pt-4 pb-4 border-b mb-8 flex justify-between items-end gap-4">
        <div>
          <div className="flex items-center gap-4 mb-1">
            <h1 className="text-3xl font-bold tracking-tight">🗑️ Discarded Papers</h1>
          </div>
          <p className="text-sm text-muted-foreground">{items?.length || 0} discarded publications. You can review them or un-discard them.</p>
        </div>
        <div className="flex items-center gap-4">
          <a 
            href={absoluteApiUrl('/api/export/bibtex/starred')}
            target="_blank"
            className="text-sm bg-secondary text-secondary-foreground px-3 py-2 rounded-md hover:bg-secondary/80 flex gap-2 items-center whitespace-nowrap font-medium"
          >
            Export All (.bib) 📥
          </a>
          <input 
            type="text" 
            placeholder="Search saved papers..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-2 border rounded-md text-sm w-64 bg-background"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="py-20 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
          <p className="mt-4 text-muted-foreground">Loading library...</p>
        </div>
      ) : (
        <>
          {filteredItems?.length === 0 && !isLoading && (
            <div className="text-center py-20 bg-card rounded-lg border border-dashed">
              <p className="text-muted-foreground text-lg mb-2">No discarded publications found</p>
              <p className="text-muted-foreground mt-4 text-center">
                You haven't discarded any papers yet.
              </p>
            </div>
          )}

          {selectedItems.length > 0 && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-foreground text-background px-6 py-3 rounded-full shadow-2xl flex items-center gap-4 z-50 animate-in slide-in-from-bottom-5">
              <span className="font-semibold text-sm">{selectedItems.length} selected</span>
              <div className="h-4 w-px bg-background/30"></div>
              <button 
                onClick={() => handleExportBibtex(selectedItems)}
                className="text-sm font-semibold hover:text-primary transition-colors flex items-center gap-2"
              >
                Export to BibTeX 📥
              </button>
              <div className="h-4 w-px bg-background/30"></div>
              <button onClick={() => setSelectedItems([])} className="text-sm opacity-80 hover:opacity-100">
                Cancel
              </button>
            </div>
          )}

          {filteredItems?.length !== 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredItems?.map(renderItemCard)}
            </div>
          )}
        </>
      )}
    </div>
  )
}
