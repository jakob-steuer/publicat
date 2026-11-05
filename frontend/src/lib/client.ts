/**
 * Typed API client. Every page goes through here, so URLs and payload shapes
 * live in one place (and this file is what an Android client would reimplement).
 */
import axios from 'axios'
import type {
  Follow,
  InboxCounts,
  InboxPage,
  InboxParams,
  Item,
  PaperSearchResult,
  Settings,
  SyncProgress,
  SyncRun,
  Topic,
  TopicModelStats,
  TopicTagState,
  TopicVote,
  Vote,
  ZoteroCollection,
  ZoteroLibraryStatus,
  ZoteroPreview,
} from '../types'
import type { TopicDraft } from '../types'
import { payloadFromDraft } from './topicDraft'

async function get<T>(url: string, params?: object): Promise<T> {
  const { data } = await axios.get<T>(url, { params })
  return data
}

export const api = {
  // ---- topics
  topics: () => get<Topic[]>('/topics/'),
  topicModels: () => get<Record<string, TopicModelStats>>('/topics/models'),
  createTopic: (draft: TopicDraft) => axios.post<Topic>('/topics/', payloadFromDraft(draft)).then(r => r.data),
  updateTopic: (id: string, draft: TopicDraft) => axios.put<Topic>(`/topics/${id}`, payloadFromDraft(draft)).then(r => r.data),
  deleteTopic: (id: string) => axios.delete(`/topics/${id}`),
  retrainTopic: (id: string) => axios.post(`/topics/${id}/retrain`),
  reorderTopics: (ids: string[]) => axios.put<Topic[]>('/topics/order', { ids }).then(r => r.data),
  searchPapers: (q: string) => get<PaperSearchResult[]>('/topics/search_papers', { q }),
  voteLeaks: () => get<{ items: number; rows: number }>('/topics/vote_leaks'),
  repairVotes: () => axios.post<{ items: number; cleared_rows: number; retraining_topics: number }>('/topics/repair_votes').then(r => r.data),

  // ---- inbox & library
  inbox: (params: InboxParams) => get<InboxPage>('/inbox/', params),
  inboxCounts: (params: Pick<InboxParams, 'min_score' | 'days' | 'show_preprints'>) => get<InboxCounts>('/inbox/counts', params),
  starred: () => get<Item[]>('/items/starred'),
  discarded: () => get<Item[]>('/items/discarded'),

  // ---- feedback
  vote: (id: string, vote: Vote, topicId?: string | null) =>
    axios.post<{ status: string; topic_id: string | null }>(`/items/${id}/vote`, { topic_id: topicId ?? null, vote }).then(r => r.data),
  bulkRescore: (ids: string[]) => axios.post('/items/bulk_rescore', { item_ids: ids }),
  tagTopic: (itemId: string, topicId: string, state: TopicTagState) =>
    axios.put<{ status: string; topic_votes: TopicVote[] }>(`/items/${itemId}/topics/${topicId}`, { state }).then(r => r.data),

  // ---- follows
  follows: () => get<Follow[]>('/follows/'),
  createFollow: (f: Omit<Follow, 'id'>) => axios.post<Follow>('/follows/', f).then(r => r.data),
  deleteFollow: (id: string) => axios.delete(`/follows/${id}`),
  searchAuthor: (q: string) => get<Array<{ authorId: string | null; name: string; paperCount?: number; hIndex?: number; affiliations?: string[] }>>('/follows/search_author', { query: q }),

  // ---- settings & sync
  settings: () => get<Settings>('/settings/'),
  saveSettings: (s: Partial<Settings>) => axios.post<Settings>('/settings/', s).then(r => r.data),
  progress: () => get<SyncProgress>('/items/progress'),
  syncRuns: (limit = 8) => get<SyncRun[]>('/items/sync_runs', { limit }),
  startFetch: (days?: number) => axios.post('/items/fetch', null, { params: days ? { days } : undefined }),
  syncControl: (action: 'pause' | 'resume' | 'abort') => axios.post('/items/sync/control', { action }),
  clearUnstarred: () => axios.delete<{ deleted: number }>('/items/unstarred').then(r => r.data),

  // ---- export
  async exportBibtex(ids: string[], filename = 'publicat_export.bib') {
    const res = await axios.post('/api/export/bibtex', { item_ids: ids }, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
  zoteroStatus: () => get<{ running: boolean }>('/api/export/zotero/status'),
  zoteroLibraryStatus: () => get<ZoteroLibraryStatus>('/zotero/status'),
  zoteroCollections: () => get<ZoteroCollection[]>('/zotero/collections'),
  zoteroPreview: (collectionKey: string | null, collectionName: string) =>
    axios.post<ZoteroPreview>('/zotero/preview', { collection_key: collectionKey, collection_name: collectionName }).then(r => r.data),
  zoteroPush: (ids: string[]) => axios.post<{ saved: number }>('/api/export/zotero/push', { item_ids: ids }).then(r => r.data),
}

/** Human-readable message from an axios error (FastAPI puts it in `detail`). */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') return detail
    return e.message
  }
  return e instanceof Error ? e.message : String(e)
}
