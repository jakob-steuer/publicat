import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { api, errorMessage } from '../../lib/client'
import { useToast } from '../../hooks/useToast'
import type { InboxPage, Item, Topic, TopicTagState, TopicVote } from '../../types'

interface Props {
  item: Item;
  topics: Topic[];
}

function stateOf(vote: number | null | undefined): TopicTagState {
  if (vote === null || vote === undefined) return 'none'
  if (vote >= 1) return 'in'
  if (vote === -1) return 'out'
  return 'none'
}

const NEXT: Record<TopicTagState, TopicTagState> = { none: 'in', in: 'out', out: 'none' }

/**
 * One chip per topic: says whether this paper belongs to the topic, wherever it
 * was found. Click cycles: no statement, belongs (trains the topic as a
 * positive), does not belong (a downvote for that topic only).
 */
export function TopicTags({ item, topics }: Props) {
  const qc = useQueryClient()
  const { toast } = useToast()

  const patchCaches = (topicVotes: TopicVote[]) => {
    qc.setQueriesData<InfiniteData<InboxPage>>({ queryKey: ['inbox'] }, old =>
      old ? { ...old, pages: old.pages.map(p => ({ ...p, items: p.items.map(i => (i.id === item.id ? { ...i, topic_votes: topicVotes } : i)) })) } : old,
    )
    qc.setQueriesData<Item[]>({ queryKey: ['library'] }, old => (old ? old.map(i => (i.id === item.id ? { ...i, topic_votes: topicVotes } : i)) : old))
  }

  const tag = useMutation({
    mutationFn: ({ topicId, state }: { topicId: string; state: TopicTagState }) => api.tagTopic(item.id, topicId, state),
    onSuccess: (r, { topicId, state }) => {
      patchCaches(r.topic_votes)
      const name = topics.find(t => t.id === topicId)?.name ?? 'topic'
      toast(state === 'in' ? `Added to "${name}"` : state === 'out' ? `Marked as not "${name}"` : `Cleared for "${name}"`, { kind: 'success', duration: 2500 })
      qc.invalidateQueries({ queryKey: ['topicModels'] })
      qc.invalidateQueries({ queryKey: ['inboxCounts'] })
    },
    onError: e => toast(errorMessage(e), { kind: 'error' }),
  })

  if (topics.length === 0) return null
  const votes = new Map((item.topic_votes ?? []).map(v => [v.topic_id, v]))

  return (
    <div>
      <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5">Topics</h3>
      <div className="flex flex-wrap gap-1.5">
        {topics.map(t => {
          const v = votes.get(t.id)
          const state = stateOf(v?.vote)
          const cls =
            state === 'in'
              ? 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200 dark:border-emerald-700'
              : state === 'out'
                ? 'bg-red-50 text-red-700 border-red-200 line-through dark:bg-red-950/40 dark:text-red-300 dark:border-red-800'
                : 'bg-muted/50 text-muted-foreground border-border hover:border-primary/40'
          const scoreText = v?.score != null ? ` · ${Math.round(Math.min(v.score, 1) * 100)}` : ''
          return (
            <button
              key={t.id}
              type="button"
              disabled={tag.isPending}
              onClick={() => tag.mutate({ topicId: t.id, state: NEXT[state] })}
              title={
                state === 'in'
                  ? `In "${t.name}". Click: mark as not belonging to this topic.`
                  : state === 'out'
                    ? `Marked as not "${t.name}". Click: clear.`
                    : `Click: add to "${t.name}" (trains that topic with this paper).`
              }
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs transition-colors ${cls}`}
            >
              {state === 'in' && <Check size={12} />}
              {state === 'out' && <X size={12} />}
              <span className="truncate max-w-[22ch]">{t.name}</span>
              <span className="tabular-nums opacity-70 no-underline">{scoreText}</span>
            </button>
          )
        })}
      </div>
      <p className="text-[11px] text-muted-foreground mt-1">Click a topic to add this paper to it, click again to mark it as not belonging, once more to clear. The number is its relevance there.</p>
    </div>
  )
}
