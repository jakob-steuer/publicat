import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import React, { useState } from 'react'
import type { Topic, Follow } from '../types'

interface AuthorResult {
  authorId: string | null;
  name: string;
  orcid?: string;
  isOrcid?: boolean;
  paperCount?: number;
  hIndex?: number;
  affiliations?: any[];
}

const fetchTopics = async () => {
  const { data } = await axios.get('http://localhost:8001/topics/')
  return data
}

const fetchSettings = async () => {
  const { data } = await axios.get('http://localhost:8001/settings/')
  return data
}

const fetchFollows = async () => {
  const { data } = await axios.get('http://localhost:8001/follows/')
  return data
}


export default function Settings() {
  const queryClient = useQueryClient()
  
  // Topic state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [keywords, setKeywords] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  // Config state
  const [geminiKey, setGeminiKey] = useState('')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [s2Key, setS2Key] = useState('')
  const [budget, setBudget] = useState('5.0')
  const [isSavingConfig, setIsSavingConfig] = useState(false)

  // Author search state
  const [authorQuery, setAuthorQuery] = useState('')
  const [authorResults, setAuthorResults] = useState<AuthorResult[]>([])
  const [isSearchingAuthor, setIsSearchingAuthor] = useState(false)

  const { data: topics, isLoading: isLoadingTopics } = useQuery({ queryKey: ['topics'], queryFn: fetchTopics })
  const { data: config } = useQuery({ 
    queryKey: ['settings'], 
    queryFn: fetchSettings,
  })

  const { data: follows, isLoading: isLoadingFollows } = useQuery({
    queryKey: ['follows'],
    queryFn: fetchFollows,
  })



  // Update local state when config loads
  React.useEffect(() => {
    if (config) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setGeminiKey(config.gemini_api_key || '')
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAnthropicKey(config.anthropic_api_key || '')
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setS2Key(config.s2_api_key || '')
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBudget(config.anthropic_budget_limit?.toString() || '5.0')
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
          const { data } = await axios.get(`http://localhost:8001/follows/search_author?query=${encodeURIComponent(authorQuery)}`)
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
    mutationFn: async (newTopic: Partial<Topic>) => {
      return axios.post('http://localhost:8001/topics/', newTopic)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
      setName('')
      setDescription('')
      setKeywords('')
      setIsCreating(false)
    },
  })

  const deleteTopic = useMutation({
    mutationFn: async (topicId: string) => {
      return axios.delete(`http://localhost:8001/topics/${topicId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    }
  })

  const saveSettings = useMutation({
    mutationFn: async (newSettings: { gemini_api_key?: string, anthropic_api_key?: string, s2_api_key?: string, anthropic_budget_limit?: number }) => {
      return axios.post('http://localhost:8001/settings/', newSettings)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setIsSavingConfig(false)
    }
  })

  const createFollow = useMutation({
    mutationFn: async (newFollow: Omit<Follow, 'id'>) => {
      return axios.post('http://localhost:8001/follows/', newFollow)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['follows'] })
    }
  })

  const deleteFollow = useMutation({
    mutationFn: async (followId: string) => {
      return axios.delete(`http://localhost:8001/follows/${followId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['follows'] })
    }
  })

  const handleCreateTopic = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name || !description) return
    setIsCreating(true)
    createTopic.mutate({ name, description, keywords: keywords || undefined, priority: 1, is_active: true })
  }

  const handleSaveConfig = (e: React.FormEvent) => {
    e.preventDefault()
    setIsSavingConfig(true)
    saveSettings.mutate({
      gemini_api_key: geminiKey,
      anthropic_api_key: anthropicKey,
      s2_api_key: s2Key,
      anthropic_budget_limit: parseFloat(budget)
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
            {topics?.map((topic: Topic) => (
              <div key={topic.id} className="flex justify-between items-center p-4 border rounded bg-background">
                <div>
                  <h3 className="font-semibold">{topic.name}</h3>
                  <p className="text-sm text-muted-foreground">{topic.description}</p>
                  {topic.keywords && <p className="text-xs text-primary mt-1 font-semibold">Keywords: {topic.keywords}</p>}
                </div>
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

        <div className="pt-4 border-t">
          <h3 className="font-semibold mb-4">Add New Topic</h3>
          <form onSubmit={handleCreateTopic} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Topic Name</label>
              <input 
                type="text" 
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Protein Design"
                className="w-full p-2 rounded border bg-background"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <textarea 
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe what you want to track to help the semantic search. e.g. Generative AI for protein design, diffusion models, structure prediction."
                className="w-full p-2 rounded border bg-background min-h-[100px]"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Keywords (Optional)</label>
              <input 
                type="text" 
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
                placeholder="Comma separated keywords, e.g. CRISPR, Cas9, Gene Editing"
                className="w-full p-2 rounded border bg-background"
              />
            </div>
            <button 
              type="submit" 
              disabled={isCreating}
              className="bg-primary text-primary-foreground px-4 py-2 rounded font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {isCreating ? 'Adding Topic (Generating Embedding)...' : 'Add Topic'}
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
            <input 
              type="text" 
              value={authorQuery}
              onChange={e => setAuthorQuery(e.target.value)}
              placeholder="e.g. Geoffrey Hinton or 0000-0002-7562-386X"
              className="w-full p-2 rounded border bg-background"
            />
            
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
                        boost_value: 0.15
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
          Provide your API keys to enable Tier 2 (Brief Summaries via Gemini) and Tier 3 (Deep Summaries via Anthropic) AI processing.
          Ollama will be used by default if keys are missing.
        </p>
        
        <form onSubmit={handleSaveConfig} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Semantic Scholar API Key (Recommended)</label>
            <input 
              type="password" 
              value={s2Key}
              onChange={e => setS2Key(e.target.value)}
              placeholder="Get one for free at semanticscholar.org/product/api"
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Gemini API Key (Tier 2)</label>
            <input 
              type="password" 
              value={geminiKey}
              onChange={e => setGeminiKey(e.target.value)}
              placeholder="AIzaSy..."
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Anthropic API Key (Tier 3)</label>
            <input 
              type="password" 
              value={anthropicKey}
              onChange={e => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Monthly Budget Cap (USD)</label>
            <input 
              type="number" 
              step="0.5"
              value={budget}
              onChange={e => setBudget(e.target.value)}
              className="w-32 p-2 rounded border bg-background"
            />
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
    </div>
  )
}
