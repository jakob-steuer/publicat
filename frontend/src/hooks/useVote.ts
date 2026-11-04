import { useCallback, useRef } from 'react'
import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { api, errorMessage } from '../lib/client'
import { useToast } from './useToast'
import type { InboxPage, Item, Vote } from '../types'

export const VOTE_LABEL: Record<string, string> = { '2': 'Starred', '1': 'Upvoted', '0': 'Marked read', '-1': 'Discarded', 'null': 'Vote removed' }

function patchItem(item: Item, vote: Vote): Item {
  return {
    ...item,
    user_vote: vote,
    is_acknowledged: vote !== null,
    is_starred: vote === 2,
    is_hidden: vote === -1,
  }
}

/**
 * Voting with optimistic cache updates, an undo stack and toasts. The inbox
 * list is deliberately not refetched on a vote so rows do not jump around
 * mid-triage; counts and model stats are.
 */
export function useVote() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const undoStack = useRef<Array<{ item: Item; prevVote: Vote; topicId: string | null }>>([])

  const applyLocally = useCallback((id: string, vote: Vote) => {
    qc.setQueriesData<InfiniteData<InboxPage>>({ queryKey: ['inbox'] }, old =>
      old ? { ...old, pages: old.pages.map(p => ({ ...p, items: p.items.map(i => (i.id === id ? patchItem(i, vote) : i)) })) } : old,
    )
    qc.setQueriesData<Item[]>({ queryKey: ['library'] }, old => (old ? old.map(i => (i.id === id ? patchItem(i, vote) : i)) : old))
  }, [qc])

  const mutation = useMutation({
    mutationFn: ({ id, vote, topicId }: { id: string; vote: Vote; topicId: string | null }) => api.vote(id, vote, topicId),
    onMutate: ({ id, vote }) => applyLocally(id, vote),
    onError: e => {
      toast(`Vote failed: ${errorMessage(e)}`, { kind: 'error' })
      qc.invalidateQueries({ queryKey: ['inbox'] })
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['inboxCounts'] })
      qc.invalidateQueries({ queryKey: ['topicModels'] })
    },
  })

  const undo = useCallback((onlyItemId?: string) => {
    const idx = onlyItemId
      ? undoStack.current.map(e => e.item.id).lastIndexOf(onlyItemId)
      : undoStack.current.length - 1
    if (idx < 0) return false
    const [entry] = undoStack.current.splice(idx, 1)
    mutation.mutate({ id: entry.item.id, vote: entry.prevVote, topicId: entry.topicId })
    toast(`Undone: ${entry.item.title.slice(0, 60)}`, { kind: 'info', duration: 2000 })
    return true
  }, [mutation, toast])

  const cast = useCallback((item: Item, vote: Vote, topicId?: string | null, options: { silent?: boolean } = {}) => {
    const prevVote = (item.user_vote ?? null) as Vote
    const next: Vote = prevVote === vote ? null : vote
    const target = topicId ?? item.topic_id ?? null
    undoStack.current.push({ item, prevVote, topicId: target })
    mutation.mutate({ id: item.id, vote: next, topicId: target })
    if (!options.silent) {
      toast(`${VOTE_LABEL[String(next)]}${item.topic_name ? ` · ${item.topic_name}` : ''}`, {
        kind: next === -1 ? 'info' : 'success',
        action: { label: 'Undo', onClick: () => undo(item.id) },
      })
    }
    return next
  }, [mutation, toast, undo])

  return { cast, undo, isPending: mutation.isPending }
}
