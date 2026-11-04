import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/client'
import type { Author, Follow } from '../types'

export function authorKey(a: Author): string | null {
  if (a.authorId) return `AUTHOR_ID:${a.authorId}`
  if (a.orcid) return `ORCID:${a.orcid}`
  return null
}

export function useFollows() {
  const qc = useQueryClient()
  const { data: follows = [] } = useQuery({ queryKey: ['follows'], queryFn: api.follows, staleTime: 60_000 })
  const invalidate = () => qc.invalidateQueries({ queryKey: ['follows'] })
  const create = useMutation({ mutationFn: api.createFollow, onSuccess: invalidate })
  const remove = useMutation({ mutationFn: api.deleteFollow, onSuccess: invalidate })

  const findFor = (a: Author): Follow | undefined => {
    const key = authorKey(a)
    return follows.find(f => f.entity_type === 'author' && (key ? f.entity_value === key : f.entity_value.toLowerCase() === a.name.toLowerCase()))
  }
  const toggle = (a: Author) => {
    const existing = findFor(a)
    if (existing) remove.mutate(existing.id)
    else create.mutate({ entity_type: 'author', entity_value: authorKey(a) ?? a.name, display_name: a.name, boost_value: 0.15 })
  }
  return { follows, findFor, toggle }
}
