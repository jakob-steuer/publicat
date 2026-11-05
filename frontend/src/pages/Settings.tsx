import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import React, { Fragment, useState } from 'react'

import type { Topic, Follow, Settings as AppSettings, TopicDraft, TopicModelStats, SyncRun } from '../types'
import { EditTopicModal } from '../components/EditTopicModal'
import { TopicForm } from '../components/TopicForm'
import { ZoteroImport } from '../components/ZoteroImport'
import { emptyDraft, payloadFromDraft } from '../lib/topicDraft'
import { useToast } from '../hooks/useToast'
import { api } from '../lib/client'

interface AuthorResult {
  authorId: string | null;
  name: string;
  orcid?: string;
  isOrcid?: boolean;
  paperCount?: number;
  hIndex?: number;
  affiliations?: string[];
}

const fetchTopics = async () => {
  const { data } = await axios.get('/topics/')
  return data
}

const fetchSettings = async () => {
  const { data } = await axios.get('/settings/')
  return data
}

const fetchFollows = async () => {
  const { data } = await axios.get('/follows/')
  return data
}


export default function Settings() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { data: zotero } = useQuery({ queryKey: ['zoteroStatus'], queryFn: api.zoteroStatus, refetchInterval: 20000, retry: false })
  const [zoteroAuto, setZoteroAuto] = useState(false)
  const [zoteroUserId, setZoteroUserId] = useState('')
  const [zoteroKey, setZoteroKey] = useState('')
  const { data: leaks } = useQuery({ queryKey: ['voteLeaks'], queryFn: api.voteLeaks })
  const { data: syncRuns } = useQuery<SyncRun[]>({ queryKey: ['syncRuns'], queryFn: () => api.syncRuns(8), refetchInterval: 30000 })
  const repairVotes = useMutation({
    mutationFn: api.repairVotes,
    onSuccess: r => {
      toast(`Fixed ${r.items} papers: ${r.cleared_rows} copied votes removed, ${r.retraining_topics} topics retraining`, { kind: 'success', duration: 6000 })
      queryClient.invalidateQueries({ queryKey: ['voteLeaks'] })
      queryClient.invalidateQueries({ queryKey: ['topicModels'] })
    },
    onError: () => toast('Repair failed', { kind: 'error' }),
  })
  
  // Topic state
  const [draft, setDraft] = useState<TopicDraft>(emptyDraft)
  const [isCreating, setIsCreating] = useState(false)
  
  // Edit Topic state
  const [editingTopic, setEditingTopic] = useState<Topic | null>(null)
  const [isEditingModalOpen, setIsEditingModalOpen] = useState(false)
  const [isUpdatingTopic, setIsUpdatingTopic] = useState(false)

  // Config state
  const [geminiKey, setGeminiKey] = useState('')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [s2Key, setS2Key] = useState('')
  const [budget, setBudget] = useState('5.0')
  const [rerankingMode, setRerankingMode] = useState('llm')
  const [isSavingConfig, setIsSavingConfig] = useState(false)

  // Author search state
  const [authorQuery, setAuthorQuery] = useState('')
  const [authorResults, setAuthorResults] = useState<AuthorResult[]>([])
  const [isSearchingAuthor, setIsSearchingAuthor] = useState(false)
  const [authorBoost, setAuthorBoost] = useState('0.15')

  const { data: topics, isLoading: isLoadingTopics } = useQuery<Topic[]>({ queryKey: ['topics'], queryFn: fetchTopics })
  const { data: topicModels } = useQuery<Record<string, TopicModelStats>>({
    queryKey: ['topicModels'],
    queryFn: async () => (await axios.get('/topics/models')).data,
    refetchInterval: 15000,
  })
  const reorderTopics = useMutation({
    mutationFn: (ids: string[]) => api.reorderTopics(ids),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['topics'] }),
  })
  const moveTopic = (index: number, delta: number) => {
    if (!topics) return
    const ids = topics.map(t => t.id)
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderTopics.mutate(ids)
  }
  const [openRun, setOpenRun] = useState<string | null>(null)
  const backfill = useMutation({
    mutationFn: (days: number) => api.startFetch(days),
    onSuccess: r => { toast(r.data?.status === 'error' ? r.data.message : 'Backfill started', { kind: r.data?.status === 'error' ? 'error' : 'info' }); queryClient.invalidateQueries({ queryKey: ['syncProgress'] }) },
  })
  const retrainTopic = useMutation({
    mutationFn: async (topicId: string) => axios.post(`/topics/${topicId}/retrain`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['topicModels'] }),
  })
  const { data: config } = useQuery<AppSettings>({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const { data: follows, isLoading: isLoadingFollows } = useQuery({
    queryKey: ['follows'],
    queryFn: fetchFollows,
  })



  // Update local state when config loads
  // The server returns API keys masked (e.g. "sk-a••••x1z9"); a masked value
  // sent back unchanged is ignored by the backend, so leaving a field alone is safe.
  React.useEffect(() => {
    if (config) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- form draft mirrors server state once it loads
      setGeminiKey(config.gemini_api_key || '')
      setAnthropicKey(config.anthropic_api_key || '')
      setS2Key(config.s2_api_key || '')
      setBudget(config.anthropic_budget_limit?.toString() || '5.0')
      setRerankingMode(config.reranking_mode || 'llm')
      setZoteroAuto(!!config.zotero_auto_push)
      setZoteroUserId(config.zotero_user_id || '')
      setZoteroKey(config.zotero_api_key || '')
    }
  }, [config])

  React.useEffect(() => {
    const delayDebounceFn = setTimeout(async () => {
      if (authorQuery.length > 2) {
        setIsSearchingAuthor(true)
        // If it looks like an ORCID, query ORCID API
        if (/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(authorQuery.trim())) {
          try {
            const orcid = authorQuery.trim();
            const { data } = await axios.get(`https://pub.orcid.org/v3.0/${orcid}/person`, {
              headers: { 'Accept': 'application/json' }
            });
            const name = data?.name?.['credit-name']?.value || `${data?.name?.['given-names']?.value || ''} ${data?.name?.['family-name']?.value || ''}`.trim() || orcid;
            setAuthorResults([{ authorId: null, name: name, orcid: orcid, isOrcid: true }]);
          } catch (e) {
            console.error("ORCID fetch error", e);
            setAuthorResults([{ authorId: null, name: authorQuery.trim(), orcid: authorQuery.trim(), isOrcid: true }]);
          }
          setIsSearchingAuthor(false);
          return
        }
        
        try {
          const { data } = await axios.get(`/follows/search_author?query=${encodeURIComponent(authorQuery)}`)
          const results = data || []
          // Sort results by paperCount descending
          results.sort((a: AuthorResult, b: AuthorResult) => (b.paperCount || 0) - (a.paperCount || 0))
          setAuthorResults(results)
        } catch (e) {
          console.error(e)
        }
        setIsSearchingAuthor(false)
      } else {
        setAuthorResults([])
      }
    }, 500)

    return () => clearTimeout(delayDebounceFn)
  }, [authorQuery])

  const createTopic = useMutation({
    mutationFn: async (payload: ReturnType<typeof payloadFromDraft>) => {
      return axios.post('/topics/', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
      queryClient.invalidateQueries({ queryKey: ['topicModels'] })
      setDraft(emptyDraft)
      setIsCreating(false)
    },
    onError: () => setIsCreating(false),
  })

  const deleteTopic = useMutation({
    mutationFn: async (topicId: string) => {
      return axios.delete(`/topics/${topicId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    }
  })

  const updateTopic = useMutation({
    mutationFn: async ({ id, draft }: { id: string, draft: TopicDraft }) => {
      return axios.put(`/topics/${id}`, payloadFromDraft(draft))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
      setIsUpdatingTopic(false)
      setIsEditingModalOpen(false)
      setEditingTopic(null)
    },
    onError: (err) => {
      console.error(err)
      setIsUpdatingTopic(false)
      toast('Failed to update topic. Is the backend running?', { kind: 'error' })
    }
  })

  const handleEditTopicSave = (id: string, topicDraft: TopicDraft) => {
    setIsUpdatingTopic(true)
    updateTopic.mutate({ id, draft: topicDraft })
  }

  const saveSettings = useMutation({
    mutationFn: async (newSettings: Partial<Omit<AppSettings, 'last_synced_at'>>) => {
      return axios.post('/settings/', newSettings)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setIsSavingConfig(false)
      toast('Settings saved', { kind: 'success' })
    },
    onError: () => { setIsSavingConfig(false); toast('Saving settings failed', { kind: 'error' }) },
  })

  const createFollow = useMutation({
    mutationFn: async (newFollow: Omit<Follow, 'id'>) => {
      return axios.post('/follows/', newFollow)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['follows'] })
    }
  })

  const deleteFollow = useMutation({
    mutationFn: async (followId: string) => {
      return axios.delete(`/follows/${followId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['follows'] })
    }
  })

  const handleCreateTopic = (e: React.FormEvent) => {
    e.preventDefault()
    if (!draft.name || !draft.description) return
    setIsCreating(true)
    createTopic.mutate(payloadFromDraft(draft))
  }

  const describeModel = (m?: TopicModelStats) => {
    if (!m) return 'No ranker yet'
    const labels = (m.n_pos ?? 0) + (m.n_neg ?? 0)
    if (!m.trained || labels === 0) return 'Ranker: description only (vote on papers to train it)'
    const auc = m.cv_auc != null ? ` · accuracy (CV AUC) ${m.cv_auc.toFixed(2)}` : ' · too few votes to measure accuracy'
    const when = m.trained_at ? ` · trained ${new Date(m.trained_at).toLocaleString()}` : ''
    const busy = m.extra?.busy ? ' · rescoring…' : ''
    return `Ranker trained on ${m.n_pos} positive / ${m.n_neg} negative votes${auc}${when}${busy}`
  }

  const handleSaveConfig = (e: React.FormEvent) => {
    e.preventDefault()
    setIsSavingConfig(true)
    saveSettings.mutate({
      gemini_api_key: geminiKey,
      anthropic_api_key: anthropicKey,
      s2_api_key: s2Key,
      anthropic_budget_limit: parseFloat(budget),
      reranking_mode: rerankingMode,
      zotero_auto_push: zoteroAuto,
      zotero_user_id: zoteroUserId,
      zotero_api_key: zoteroKey,
    })
  }

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-8 pb-20">
      <div>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Settings</h1>
        <p className="text-muted-foreground">Manage your research interests, topics, and application preferences.</p>
      </div>

      <div className="border rounded-lg p-6 bg-card shadow-sm">
        <h2 className="text-xl font-semibold mb-4">Your Topics</h2>
        {isLoadingTopics ? (
          <p>Loading topics...</p>
        ) : (
          <div className="space-y-4 mb-6">
            {topics?.map((topic: Topic, index: number) => (
              <div key={topic.id} className="flex justify-between items-center p-4 border rounded bg-background gap-4">
                <div className="flex flex-col gap-1 shrink-0">
                  <button onClick={() => moveTopic(index, -1)} disabled={index === 0} className="w-6 h-6 rounded border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-30" title="Move up">▲</button>
                  <button onClick={() => moveTopic(index, 1)} disabled={index === (topics?.length ?? 0) - 1} className="w-6 h-6 rounded border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-30" title="Move down">▼</button>
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold">{topic.name}</h3>
                  <p className="text-sm text-muted-foreground">{topic.description}</p>
                  {topic.keywords && <p className="text-xs text-primary mt-1 font-semibold">Keywords: {topic.keywords}</p>}
                  {topic.exclude_keywords && <p className="text-xs text-destructive mt-0.5 font-semibold">Excludes: {topic.exclude_keywords}</p>}
                  <p className="text-xs text-muted-foreground mt-1">
                    {topic.seed_papers?.length ? `${topic.seed_papers.length} seed papers` : 'No seed papers (topic vector from description search)'}
                    {' · '}{describeModel(topicModels?.[topic.id])}
                  </p>
                </div>
                  <button 
                    onClick={() => retrainTopic.mutate(topic.id)}
                    className="text-muted-foreground hover:bg-muted px-3 py-1 rounded transition-colors mr-2 text-sm"
                    title="Rebuild topic vector, retrain the ranker on your votes and rescore all papers"
                  >
                    Retrain
                  </button>
                  <button 
                    onClick={() => {
                      setEditingTopic(topic)
                      setIsEditingModalOpen(true)
                    }}
                    className="text-primary hover:bg-primary/10 px-3 py-1 rounded transition-colors mr-2"
                  >
                    Edit
                  </button>
                  <button 
                    onClick={() => deleteTopic.mutate(topic.id)}
                    className="text-destructive hover:bg-destructive/10 px-3 py-1 rounded transition-colors"
                  >
                    Delete
                  </button>
              </div>
            ))}
            {topics?.length === 0 && <p className="text-muted-foreground text-sm">No topics added yet.</p>}
          </div>
        )}

        {leaks && leaks.items > 0 && (
          <div className="mb-6 border border-amber-300/60 bg-amber-50/60 dark:bg-amber-950/20 rounded-lg p-4 text-sm">
            <p className="font-semibold mb-1">Votes copied across topics: {leaks.items} papers ({leaks.rows} rows)</p>
            <p className="text-muted-foreground mb-3">Older versions wrote a vote made on the overview page to every topic the paper matched, so topics learned from each other's feedback. The repair keeps each of these votes only on the topic the paper fits best and retrains.</p>
            <button onClick={() => repairVotes.mutate()} disabled={repairVotes.isPending} className="px-3 py-1.5 rounded bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50">
              {repairVotes.isPending ? 'Repairing…' : 'Repair leaked votes'}
            </button>
          </div>
        )}

        <div className="pt-4 border-t">
          <h3 className="font-semibold mb-4">Add New Topic</h3>
          <div className="mb-4"><ZoteroImport onDraft={setDraft} /></div>
          <form onSubmit={handleCreateTopic} className="space-y-4">
            <TopicForm draft={draft} onChange={setDraft} />
            <button 
              type="submit" 
              disabled={isCreating}
              className="bg-primary text-primary-foreground px-4 py-2 rounded font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {isCreating ? 'Adding Topic...' : 'Add Topic'}
            </button>
          </form>
        </div>
      </div>

      <div className="border rounded-lg p-6 bg-card shadow-sm relative z-50">
        <h2 className="text-xl font-semibold mb-4">Followed Authors</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Track specific authors. Papers matching these will receive a static score boost (+0.15 by default), making them more likely to be highlighted and summarized.
        </p>
        
        {isLoadingFollows ? (
          <p>Loading follows...</p>
        ) : (
          <div className="mb-6">
            <h3 className="text-sm font-semibold mb-2 text-muted-foreground">Authors</h3>
            <div className="flex flex-wrap gap-2 mb-4">
              {follows?.filter((f: Follow) => f.entity_type === 'author').map((follow: Follow) => (
                <div key={follow.id} className="flex items-center gap-1.5 bg-secondary text-secondary-foreground px-3 py-1.5 rounded-full text-sm border border-border/50 shadow-sm">
                  <span className="font-medium">{follow.display_name || follow.entity_value}</span>
                  <span className="text-[10px] text-muted-foreground bg-background/50 px-1.5 rounded-full">+{follow.boost_value.toFixed(2)}</span>
                  <button 
                    onClick={() => deleteFollow.mutate(follow.id)}
                    className="ml-1 text-muted-foreground hover:text-destructive transition-colors focus:outline-none"
                    title="Remove Author"
                  >
                    ×
                  </button>
                </div>
              ))}
              {follows?.filter((f: Follow) => f.entity_type === 'author').length === 0 && (
                <p className="text-xs text-muted-foreground italic">No authors followed.</p>
              )}
            </div>
          </div>
        )}

        <div className="pt-4 border-t relative">
          <h3 className="font-semibold mb-4">Add New Follow</h3>
          <div className="flex flex-col gap-2 relative">
            <label className="block text-sm font-medium">Search Author or paste ORCID</label>
            <p className="text-[11px] text-muted-foreground font-medium mb-1">
              Adding authors via ORCID is highly recommended for best accuracy.
            </p>
            <div className="flex gap-2">
              <input 
                type="text" 
                value={authorQuery}
                onChange={e => setAuthorQuery(e.target.value)}
                placeholder="e.g. Geoffrey Hinton or 0000-0002-7562-386X"
                className="w-full p-2 rounded border bg-background"
              />
              <div className="flex items-center gap-2 whitespace-nowrap">
                <label className="text-sm font-medium text-muted-foreground">Boost:</label>
                <input 
                  type="number" 
                  step="0.05"
                  value={authorBoost}
                  onChange={e => setAuthorBoost(e.target.value)}
                  className="w-20 p-2 rounded border bg-background"
                  title="Score boost value for this author"
                />
              </div>
            </div>
            
            {isSearchingAuthor && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-card border rounded-md shadow-lg z-10 p-4 text-center text-sm text-muted-foreground">
                Searching Semantic Scholar...
              </div>
            )}
            
            {authorResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-zinc-900 border rounded-md shadow-xl z-[100] max-h-60 overflow-y-auto ring-1 ring-border opacity-100">
                {authorResults.map((author, idx) => (
                  <button
                    key={author.authorId || idx}
                    className="w-full text-left px-4 py-3 hover:bg-secondary border-b last:border-b-0 transition-colors flex justify-between items-center"
                    onClick={() => {
                      const entity_value = author.isOrcid ? `ORCID:${author.orcid}` : `AUTHOR_ID:${author.authorId}`
                      const display_name = author.name
                      createFollow.mutate({
                        entity_type: 'author',
                        entity_value: entity_value,
                        display_name: display_name,
                        boost_value: parseFloat(authorBoost) || 0.15
                      })
                      setAuthorQuery('')
                      setAuthorResults([])
                    }}
                  >
                    <div>
                      <div className="font-medium text-foreground">{author.name}</div>
                      {author.isOrcid ? (
                        <div className="text-xs text-primary">ORCID: {author.orcid}</div>
                      ) : (
                        <div className="text-xs text-muted-foreground flex flex-col gap-0.5">
                          <div>
                            {author.paperCount ? `${author.paperCount} papers` : ''} 
                            {author.hIndex ? ` • h-index: ${author.hIndex}` : ''}
                          </div>
                          {author.affiliations && author.affiliations.length > 0 && (
                            <div className="text-foreground/70 truncate max-w-[400px]">
                              🏛️ {author.affiliations.join(", ")}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="text-xs bg-primary text-primary-foreground px-3 py-1.5 rounded shadow-sm hover:bg-primary/90 transition-colors ml-4">Add</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border rounded-lg p-6 bg-card shadow-sm">
        <h2 className="text-xl font-semibold mb-4">API Keys</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Provide an API key to enable AI summaries and keyword extraction. You only need to provide ONE key. If both are provided, Anthropic will be prioritized. If no key is provided, a local Ollama instance is used.
        </p>
        
        <form onSubmit={handleSaveConfig} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">
              Semantic Scholar API Key
            </label>
            {!s2Key && (
              <p className="text-xs text-foreground font-bold mb-2">
                Highly Recommended: Without this key, fetching will likely fail due to rate limits.
              </p>
            )}
            <input 
              type="password" 
              value={s2Key}
              onChange={e => setS2Key(e.target.value)}
              placeholder="Get one for free at semanticscholar.org/product/api"
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Gemini API Key (Gemini 2.5 Flash)</label>
            <input 
              type="password" 
              value={geminiKey}
              onChange={e => setGeminiKey(e.target.value)}
              placeholder="AIzaSy..."
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Anthropic API Key (Claude 3.5 Haiku)</label>
            <input 
              type="password" 
              value={anthropicKey}
              onChange={e => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Monthly cloud LLM budget (USD) <span className="text-muted-foreground font-normal">· spent this month: ${(config?.llm_spend_this_month ?? 0).toFixed(3)}</span></label>
            <input 
              type="number" 
              step="0.5"
              value={budget}
              onChange={e => setBudget(e.target.value)}
              className="w-32 p-2 rounded border bg-background"
            />
          </div>
          <div className="border-t mt-4 pt-4 space-y-3 pb-2">
            <label className="block text-sm font-medium">Stage 2 LLM Reranking / Rescoring</label>
            <div className="flex flex-col sm:flex-row gap-4 sm:items-center text-sm text-foreground/80 cursor-pointer">
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="radio" 
                  name="reranking_mode" 
                  value="llm" 
                  checked={rerankingMode === 'llm'}
                  onChange={e => setRerankingMode(e.target.value)}
                  className="accent-primary"
                />
                Use API (Anthropic/Gemini)
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="radio" 
                  name="reranking_mode" 
                  value="local" 
                  checked={rerankingMode === 'local'}
                  onChange={e => setRerankingMode(e.target.value)}
                  className="accent-primary"
                />
                Use Local (Ollama)
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="radio" 
                  name="reranking_mode" 
                  value="disabled" 
                  checked={rerankingMode === 'disabled'}
                  onChange={e => setRerankingMode(e.target.value)}
                  className="accent-primary"
                />
                Disabled
              </label>
            </div>
            <p className="text-xs text-muted-foreground mt-2">Choose 'Disabled' to skip stage 2 AI reranking entirely (saves API tokens and speeds up syncs). Choose 'Use Local' to enforce using Ollama even if you provided API keys above.</p>
          </div>
          <button 
            type="submit" 
            disabled={isSavingConfig}
            className="bg-primary text-primary-foreground px-4 py-2 rounded font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isSavingConfig ? 'Saving...' : 'Save Configuration'}
          </button>
        </form>
      </div>


      <div className="border rounded-lg p-6 bg-card shadow-sm">
        <h2 className="text-xl font-semibold mb-2">Recent syncs</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Each fetch looks back to the last <em>complete</em> sync (at least 3, at most 30 days). A run with failed requests is marked partial and its period is fetched again next time, so a lost connection or a closed laptop never leaves a gap.
          {config?.last_complete_sync_at && <> Last complete sync: {new Date(config.last_complete_sync_at).toLocaleString()}.</>}
        </p>
        {!syncRuns?.length ? (
          <p className="text-sm text-muted-foreground italic">No syncs recorded yet.</p>
        ) : (
          <>
          <div className="mb-3">
            <button onClick={() => backfill.mutate(30)} disabled={backfill.isPending} className="text-xs px-2.5 py-1.5 rounded-md border border-border hover:bg-muted font-semibold" title="Fetch the last 30 days for all topics, e.g. after adding topics">Fetch the last 30 days</button>
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground text-left">
              <tr><th className="py-1 pr-3 font-medium">When</th><th className="py-1 pr-3 font-medium">Job</th><th className="py-1 pr-3 font-medium">Result</th><th className="py-1 pr-3 font-medium text-right">Window</th><th className="py-1 pr-3 font-medium text-right">New</th><th className="py-1 font-medium text-right">Errors</th></tr>
            </thead>
            <tbody>
              {syncRuns.map(r => (
                <Fragment key={r.id}>
                <tr className="border-t border-border/60 cursor-pointer hover:bg-muted/40" title="Click for per-source details" onClick={() => setOpenRun(o => (o === r.id ? null : r.id))}>
                  <td className="py-1.5 pr-3 whitespace-nowrap">{new Date(r.started_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                  <td className="py-1.5 pr-3 truncate max-w-[16ch]">{r.job}</td>
                  <td className={`py-1.5 pr-3 font-medium ${r.status === 'complete' ? 'text-emerald-600' : r.status === 'running' ? 'text-primary' : r.status === 'partial' ? 'text-amber-600' : 'text-red-600'}`}>{r.status}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{r.days_back ?? '–'} d</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{r.counters?.stored ?? '–'}</td>
                  <td className="py-1.5 text-right tabular-nums">{r.errors}</td>
                </tr>
                {openRun === r.id && (
                  <tr className="bg-muted/30">
                    <td colSpan={6} className="px-3 py-3 text-xs">
                      {r.counters?.sources ? (
                        <table className="w-full mb-2">
                          <thead className="text-muted-foreground text-left"><tr><th className="font-medium pr-3">Source</th><th className="font-medium pr-3 text-right">Returned</th><th className="font-medium pr-3 text-right">In date window</th><th className="font-medium text-right">Stored</th></tr></thead>
                          <tbody>
                            {Object.entries(r.counters.sources).map(([name, [returned, kept]]) => (
                              <tr key={name} className={returned === 0 ? 'text-amber-600' : ''}>
                                <td className="pr-3">{name}</td><td className="pr-3 text-right tabular-nums">{returned}</td><td className="pr-3 text-right tabular-nums">{kept}</td><td className="text-right tabular-nums">{r.counters.stored_by_source?.[name] ?? 0}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : <p className="text-muted-foreground mb-2">No per-source counts recorded for this run.</p>}
                      <p className="text-muted-foreground">
                        {r.counters?.discovered ?? 0} candidates · {r.counters?.new_candidates ?? 0} not yet known · {r.counters?.enriched ?? 0} with metadata in the window · {r.counters?.stored ?? 0} stored · {r.counters?.cleaned_up ?? 0} old papers removed
                      </p>
                      {r.message && <p className="mt-1 text-amber-700 dark:text-amber-400">{r.message}</p>}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
          </>
        )}
      </div>

      <div className="border rounded-lg p-6 bg-card shadow-sm">
        <h2 className="text-xl font-semibold mb-2">Zotero</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Papers can be saved straight into the running Zotero desktop app (into the collection currently selected there), with the AI summary as a note. No API key needed.
          {' '}Status: {zotero?.running ? <span className="text-emerald-600 font-semibold">Zotero is running</span> : <span className="text-muted-foreground">Zotero desktop not detected on this machine</span>}.
        </p>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={zoteroAuto} onChange={e => setZoteroAuto(e.target.checked)} className="accent-primary" />
          Automatically save every starred paper to Zotero
        </label>
        <div className="grid sm:grid-cols-2 gap-3 mt-4">
          <div>
            <label className="block text-sm font-medium mb-1">Zotero user ID <span className="text-muted-foreground font-normal">(optional)</span></label>
            <input type="text" value={zoteroUserId} onChange={e => setZoteroUserId(e.target.value)} placeholder="e.g. 1234567" className="w-full p-2 rounded border bg-background" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Zotero API key <span className="text-muted-foreground font-normal">(read-only is enough)</span></label>
            <input type="password" value={zoteroKey} onChange={e => setZoteroKey(e.target.value)} placeholder="from zotero.org/settings/keys" className="w-full p-2 rounded border bg-background" />
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-2">User ID and key are only needed to read your library for topic import when the desktop app is not running on this machine. Saved together with the API keys below. The RSS feed (button in the inbox header) keeps working as a fallback.</p>
      </div>

      <div className="border border-red-200 dark:border-red-900/50 rounded-lg p-6 bg-red-50/50 dark:bg-red-950/20 shadow-sm mt-8">
        <h2 className="text-xl font-semibold mb-2 text-red-700 dark:text-red-400">Data Management</h2>
        <p className="text-sm text-red-600/80 dark:text-red-400/80 mb-6">
          Permanently delete all papers from your local database that are neither starred nor voted on. Voted papers are kept because they train the ranking. This action cannot be undone.
        </p>
        
        <button 
          onClick={async () => {
            if(window.confirm('Delete all papers that are neither starred nor voted on? This action cannot be undone.')) {
              try {
                const res = await axios.delete('/items/unstarred');
                toast(`Deleted ${res.data.deleted} papers`, { kind: 'success' });
                queryClient.invalidateQueries();
              } catch {
                toast('Failed to clear papers', { kind: 'error' });
              }
            }
          }}
          className="bg-red-600 text-white px-4 py-2 rounded font-medium hover:bg-red-700 transition-colors"
        >
          Clear Unstarred Inbox
        </button>
      </div>
      <EditTopicModal 
        key={editingTopic ? `${editingTopic.id}:${editingTopic.name}:${editingTopic.description}:${editingTopic.keywords ?? ''}` : 'none'}
        isOpen={isEditingModalOpen}
        onClose={() => setIsEditingModalOpen(false)}
        topic={editingTopic}
        onSave={handleEditTopicSave}
        isSaving={isUpdatingTopic}
      />
    </div>
  )
}
