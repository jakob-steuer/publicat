import React, { useState } from 'react'
import type { Topic, TopicDraft } from '../types'
import { TopicForm } from './TopicForm'
import { draftFromTopic } from '../lib/topicDraft'

interface EditTopicModalProps {
  topic: Topic | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (id: string, draft: TopicDraft) => void;
  isSaving: boolean;
}

/**
 * The parent renders this with a `key` derived from the topic so the draft is
 * initialised from the topic on mount and reset whenever another topic is edited.
 */
export function EditTopicModal({ topic, isOpen, onClose, onSave, isSaving }: EditTopicModalProps) {
  const [draft, setDraft] = useState<TopicDraft>(() => (topic ? draftFromTopic(topic) : { name: '', description: '', keywords: '', exclude_keywords: '', seed_papers: [], arxiv_categories: [] }))

  if (!isOpen || !topic) return null

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(topic.id, draft)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-zinc-950 border border-border rounded-xl shadow-2xl w-full max-w-2xl p-6 relative max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 text-muted-foreground hover:text-foreground" aria-label="Close">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>

        <h2 className="text-xl font-bold mb-6">Edit Topic</h2>

        <form onSubmit={handleSave} className="space-y-4">
          <TopicForm draft={draft} onChange={setDraft} />
          <p className="text-xs text-muted-foreground">Saving rebuilds the topic vector, retrains the ranker on your votes and rescores every paper in the background.</p>
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded font-medium border border-border hover:bg-muted transition-colors">Cancel</button>
            <button type="submit" disabled={isSaving} className="px-4 py-2 rounded font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2">
              {isSaving ? 'Saving & Rescoring...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
