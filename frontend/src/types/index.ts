export interface Author {
  name: string;
  authorId?: string;
  orcid?: string;
}

export interface Item {
  id: string;
  title: string;
  abstract?: string;
  url: string;
  doi?: string;
  authors: string[];
  author_details?: Author[];
  published_at: string;
  venue?: string;
  corpus_id?: string;
  citation_count?: number;
  influential_citation_count?: number;
  reference_count?: number;
  is_open_access?: boolean;
  open_access_pdf_url?: string;
  t1_tldr?: string;
  t2_summary?: string;
  t3_summary?: string;
  tools?: string[];
  source?: string;
  is_acknowledged: boolean;
  is_starred: boolean;
  is_hidden: boolean;
  /** Relevance for the topic in `topic_id` (best topic on the overview). */
  score?: number;
  user_vote?: number | null;
  /** The topic a vote on this card is attributed to. */
  topic_id?: string | null;
  topic_name?: string | null;
  /** Human-readable explanation of the score, strongest factor first. */
  reasons?: string[];
  /** Shown from just below the relevance threshold to counter the filter bubble. */
  wildcard?: boolean;
  /** Discovery lanes that found this paper, e.g. ["arXiv", "S2 search"]. */
  discovered_via?: string[] | null;
  /** Score and vote of this paper in every topic it has been scored for. */
  topic_votes?: TopicVote[];
}

export interface TopicVote {
  topic_id: string;
  topic_name: string;
  score: number | null;
  vote: number | null;
}

export type TopicTagState = 'in' | 'out' | 'none'

export type Vote = 2 | 1 | 0 | -1 | null

export interface VotePayload {
  id: string;
  vote: Vote;
  topicId?: string | null;
}

export interface SeedPaper {
  paperId: string;
  title?: string;
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  keywords?: string | null;
  exclude_keywords?: string | null;
  seed_papers?: SeedPaper[] | null;
  arxiv_categories?: string[] | null;
  priority?: number;
  is_active?: boolean;
  has_prior_vector?: boolean;
}

export interface TopicDraft {
  name: string;
  description: string;
  keywords: string;
  exclude_keywords: string;
  seed_papers: SeedPaper[];
  arxiv_categories: string[];
}

export interface TopicModelStats {
  topic_id: string;
  trained: boolean;
  n_pos: number;
  n_neg: number;
  cv_auc?: number | null;
  trained_at?: string | null;
  prior_source?: string | null;
  extra?: { labels?: number; busy?: boolean };
}

export interface PaperSearchResult {
  paperId: string;
  title?: string;
  year?: number;
  venue?: string;
  authors?: string[];
}

export interface ZoteroCollection {
  key: string;
  name: string;
  path: string;
  parent: string | null;
  num_items: number;
}

export interface ZoteroPreview {
  name: string;
  description: string;
  suggested_keywords: string[];
  seed_papers: SeedPaper[];
  total_items: number;
  matched: number;
  unresolved_titles: string[];
  unresolved_count: number;
  source: string;
}

export interface ZoteroLibraryStatus {
  available: boolean;
  local: { reachable: boolean; message: string | null };
  web: { reachable: boolean; message: string | null };
}

export interface Follow {
  id: string;
  entity_type: string;
  entity_value: string;
  display_name?: string;
  boost_value: number;
}

export interface SyncProgress {
  status: string;
  message: string;
  progress: number;
  job?: string | null;
  errors?: number;
}

export interface Settings {
  gemini_api_key: string;
  anthropic_api_key: string;
  s2_api_key: string;
  anthropic_budget_limit: number;
  enable_llm_reranking: boolean;
  reranking_mode: string;
  zotero_auto_push: boolean;
  zotero_user_id?: string;
  zotero_api_key?: string;
  llm_spend_this_month?: number;
  last_synced_at?: string;
  last_complete_sync_at?: string | null;
}

export interface SyncRun {
  id: string;
  job: string;
  status: 'running' | 'complete' | 'partial' | 'aborted' | 'error' | 'interrupted';
  days_back?: number | null;
  started_at: string;
  finished_at?: string | null;
  errors: number;
  counters: {
    discovered?: number;
    new_candidates?: number;
    enriched?: number;
    stored?: number;
    cleaned_up?: number;
    /** lane -> [returned by the source, within the date window] */
    sources?: Record<string, [number, number]>;
    stored_by_source?: Record<string, number>;
    error_messages?: string[];
  };
  message?: string | null;
}

export type InboxFilter = 'all' | 'top' | 'week' | 'month' | 'authors' | 'starred'
export type InboxSort = 'score' | 'date'

export interface InboxParams {
  topic_id?: string;
  author_id?: string;
  min_score?: number;
  days?: number;
  show_acknowledged?: boolean;
  show_preprints?: boolean;
  show_discarded?: boolean;
  q?: string;
  filter?: InboxFilter;
  sort?: InboxSort;
  limit?: number;
  offset?: number;
  wildcards?: number;
}

export interface InboxPage {
  items: Item[];
  total: number;
  offset: number;
  limit: number;
}

export interface InboxCounts {
  all: number;
  topics: Record<string, number>;
}

export interface Dashboard {
  do_not_miss: Item[];
  this_week: Item[];
  this_month: Item[];
  starred: Item[];
  highlighted_authors: Item[];
  trending: Item[];
  tools: Item[];
  feed_sections?: Record<string, Item[]>;
}
