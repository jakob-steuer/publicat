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
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  keywords?: string;
  priority?: number;
  is_active?: boolean;
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
}

export interface Settings {
  last_synced_at?: string;
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
