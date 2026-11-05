import type { SeedPaper, TopicDraft } from '../types'

export const emptyDraft: TopicDraft = {
  name: '',
  description: '',
  keywords: '',
  exclude_keywords: '',
  seed_papers: [],
  arxiv_categories: [],
}

export function draftFromTopic(t: { name: string; description: string; keywords?: string | null; exclude_keywords?: string | null; seed_papers?: SeedPaper[] | null; arxiv_categories?: string[] | null }): TopicDraft {
  return {
    name: t.name,
    description: t.description,
    keywords: t.keywords ?? '',
    exclude_keywords: t.exclude_keywords ?? '',
    seed_papers: t.seed_papers ?? [],
    arxiv_categories: t.arxiv_categories ?? [],
  }
}

export function payloadFromDraft(d: TopicDraft) {
  return {
    name: d.name,
    description: d.description,
    keywords: d.keywords.trim() || null,
    exclude_keywords: d.exclude_keywords.trim() || null,
    seed_papers: d.seed_papers.length ? d.seed_papers : null,
    arxiv_categories: d.arxiv_categories.length ? d.arxiv_categories : null,
  }
}
