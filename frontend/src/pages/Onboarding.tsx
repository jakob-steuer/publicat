import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../lib/client'
import { TopicForm } from '../components/TopicForm'
import { emptyDraft } from '../lib/topicDraft'
import { useToast } from '../hooks/useToast'
import type { TopicDraft } from '../types'

/** Shown instead of the inbox while there are no topics: key, first topic, first fetch. */
export function Onboarding() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const [s2Key, setS2Key] = useState('')
  const [draft, setDraft] = useState<TopicDraft>(emptyDraft)
  const hasKey = !!settings?.s2_api_key

  const saveKey = useMutation({
    mutationFn: () => api.saveSettings({ s2_api_key: s2Key.trim() }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['settings'] }); toast('Semantic Scholar key saved', { kind: 'success' }) },
    onError: e => toast(errorMessage(e), { kind: 'error' }),
  })
  const createTopic = useMutation({
    mutationFn: () => api.createTopic(draft),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['topics'] }); toast('Topic created. Fetching the last 30 days of papers…', { kind: 'success', duration: 6000 }) },
    onError: e => toast(errorMessage(e), { kind: 'error' }),
  })

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Welcome to Publicat</h1>
        <p className="text-muted-foreground">Three steps and your first ranked feed is on its way. Everything runs locally; papers come from Semantic Scholar, arXiv and bioRxiv.</p>
      </div>

      <section className={`border rounded-xl p-5 ${hasKey ? 'bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-300/50' : 'bg-card'}`}>
        <h2 className="font-semibold mb-1">1. Semantic Scholar API key {hasKey && <span className="text-emerald-600 text-sm font-normal">✓ saved</span>}</h2>
        <p className="text-sm text-muted-foreground mb-3">Free at <a className="text-primary hover:underline" href="https://www.semanticscholar.org/product/api" target="_blank" rel="noopener noreferrer">semanticscholar.org/product/api</a>. Without it the shared rate limit makes fetching unreliable.</p>
        {!hasKey && (
          <form className="flex gap-2" onSubmit={e => { e.preventDefault(); if (s2Key.trim()) saveKey.mutate() }}>
            <input type="password" value={s2Key} onChange={e => setS2Key(e.target.value)} placeholder="Paste your key" className="flex-1 p-2 rounded border bg-background" />
            <button type="submit" disabled={saveKey.isPending || !s2Key.trim()} className="px-4 py-2 rounded bg-primary text-primary-foreground font-medium disabled:opacity-50">Save</button>
          </form>
        )}
      </section>

      <section className="border rounded-xl p-5 bg-card">
        <h2 className="font-semibold mb-1">2. Your first topic</h2>
        <p className="text-sm text-muted-foreground mb-4">Describe it, then add a few seed papers you consider perfect examples. The seed papers define what "relevant" means; your votes refine it from there.</p>
        <form className="space-y-4" onSubmit={e => { e.preventDefault(); if (draft.name && draft.description) createTopic.mutate() }}>
          <TopicForm draft={draft} onChange={setDraft} />
          <button type="submit" disabled={createTopic.isPending || !draft.name || !draft.description} className="px-4 py-2 rounded bg-primary text-primary-foreground font-medium disabled:opacity-50">
            {createTopic.isPending ? 'Creating…' : 'Create topic and fetch papers'}
          </button>
        </form>
      </section>

      <section className="border rounded-xl p-5 bg-muted/30">
        <h2 className="font-semibold mb-1">3. Triage</h2>
        <p className="text-sm text-muted-foreground">The first fetch takes a few minutes. Then work through the inbox with <kbd className="px-1 border rounded font-mono text-xs">s</kbd> star, <kbd className="px-1 border rounded font-mono text-xs">u</kbd> up, <kbd className="px-1 border rounded font-mono text-xs">n</kbd> read, <kbd className="px-1 border rounded font-mono text-xs">d</kbd> discard. Every vote retrains the topic within seconds. The <Link to="/help" className="text-primary hover:underline">guide</Link> has the rest.</p>
      </section>
    </div>
  )
}
