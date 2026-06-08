import React, { useState, useEffect } from 'react'
import type { Topic } from '../types'

interface EditTopicModalProps {
  topic: Topic | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (id: string, name: string, description: string, keywords: string) => void;
  isSaving: boolean;
}

export function EditTopicModal({ topic, isOpen, onClose, onSave, isSaving }: EditTopicModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [keywords, setKeywords] = useState('')

  useEffect(() => {
    if (topic && isOpen) {
      setName(topic.name)
      setDescription(topic.description)
      setKeywords(topic.keywords || '')
    }
  }, [topic, isOpen])

  if (!isOpen || !topic) return null

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(topic.id, name, description, keywords)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-xl shadow-lg w-full max-w-lg p-6 relative">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
        
        <h2 className="text-xl font-bold mb-6">Edit Topic</h2>
        
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Topic Name</label>
            <input 
              type="text" 
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full p-2 rounded border bg-background"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea 
              value={description}
              onChange={e => setDescription(e.target.value)}
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
              placeholder="Comma separated keywords"
              className="w-full p-2 rounded border bg-background"
            />
          </div>
          
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button 
              type="button" 
              onClick={onClose}
              className="px-4 py-2 rounded font-medium border border-border hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button 
              type="submit" 
              disabled={isSaving}
              className="px-4 py-2 rounded font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {isSaving ? 'Saving & Rescoring...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
