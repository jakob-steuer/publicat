/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import type { UseMutationResult } from '@tanstack/react-query'
import type { Item, Follow } from '../types'

interface ItemCardProps {
  item: Item & { score?: number };
  selectedItems: string[];
  toggleSelect: (id: string) => void;
  follows: Follow[];
  createFollow: UseMutationResult<any, Error, any, unknown>;
  deleteFollow: UseMutationResult<any, Error, string, unknown>;
  starItem: UseMutationResult<any, Error, string, unknown>;
  unstarItem: UseMutationResult<any, Error, string, unknown>;
  acknowledgeItem: UseMutationResult<any, Error, string, unknown>;
  unacknowledgeItem: UseMutationResult<any, Error, string, unknown>;
  hideItem: UseMutationResult<any, Error, string, unknown>;
  unhideItem?: UseMutationResult<any, Error, string, unknown>;
}

export function ItemCard({
  item,
  selectedItems,
  toggleSelect,
  follows,
  createFollow,
  deleteFollow,
  starItem,
  unstarItem,
  acknowledgeItem,
  unacknowledgeItem,
  hideItem,
  unhideItem
}: ItemCardProps) {
  const [expandedAuthors, setExpandedAuthors] = useState(false)
  const isLongAuthorList = (item.author_details?.length ?? item.authors?.length ?? 0) > 8
  
  return (
    <div key={item.id} className="relative flex flex-col justify-between bg-card rounded-md border-t-4 border-t-primary/80 border-x border-b shadow-sm hover:shadow-md transition-shadow p-5 pt-6 group mt-4">
      {/* Top left score */}
      {item.score !== undefined && item.score !== null && (
        <div 
          className={`absolute -top-2 -left-2 w-8 h-8 rounded-full border flex items-center justify-center font-bold text-[10px] shadow-sm
            ${item.score >= 0.9 ? 'bg-emerald-100 text-emerald-800 border-emerald-300' :
              item.score >= 0.75 ? 'bg-green-100 text-green-700 border-green-200' : 
              item.score >= 0.6 ? 'bg-yellow-100 text-yellow-700 border-yellow-200' : 
              item.score >= 0.4 ? 'bg-orange-100 text-orange-700 border-orange-200' :
              'bg-red-100 text-red-700 border-red-200'}`}
          title={`Relevance: ${(item.score * 100).toFixed(0)}%`}
        >
          {(item.score * 100).toFixed(0)}
        </div>
      )}

      {/* Top right actions */}
      <div className="absolute top-4 right-4 flex gap-2 items-center">
        <input 
          type="checkbox" 
          className="w-4 h-4 mr-1 accent-primary cursor-pointer"
          checked={selectedItems.includes(item.id)}
          onChange={() => toggleSelect(item.id)}
          title="Select for export"
        />
        <button 
          onClick={() => item.is_starred ? unstarItem.mutate(item.id) : starItem.mutate(item.id)}
          className="hover:scale-110 transition-transform p-1 bg-background/50 rounded-full"
          title={item.is_starred ? "Unstar" : "Star"}
        >
          {item.is_starred ? '⭐' : '☆'}
        </button>
        {!item.is_acknowledged ? (
          <button 
            onClick={() => acknowledgeItem.mutate(item.id)}
            className="hover:scale-110 transition-transform p-1 bg-background/50 rounded-full text-green-600 dark:text-green-400 font-bold"
            title="Mark as Read"
          >
            ✓
          </button>
        ) : (
          <button 
            onClick={() => unacknowledgeItem.mutate(item.id)}
            className="hover:scale-110 transition-transform p-1 bg-background/50 rounded-full text-muted-foreground font-bold"
            title="Mark as Unread"
          >
            ↩
          </button>
        )}
        {item.is_hidden && unhideItem ? (
          <button 
            onClick={() => unhideItem.mutate(item.id)}
            className="hover:scale-110 transition-transform p-1 bg-background/50 rounded-full text-blue-500 font-bold ml-1"
            title="Recover / Unhide"
          >
            ↩️
          </button>
        ) : (
          <button 
            onClick={() => hideItem.mutate(item.id)}
            className="hover:scale-110 transition-transform p-1 bg-background/50 rounded-full text-red-500 font-bold ml-1 text-sm flex items-center justify-center w-7 h-7"
            title="Dismiss / Hide"
          >
            ✕
          </button>
        )}
      </div>
      
      <div>
        {/* 1. The Summary (Hero content) */}
        <div className="mb-4">
          {(item.t3_summary || item.t1_tldr || item.t2_summary) && (
            <div className="mb-2">
              <span className="font-sans font-bold text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded uppercase border border-blue-200 shadow-sm">
                AI Summary
              </span>
            </div>
          )}
          {item.t3_summary ? (
            <p className="font-serif text-[15px] leading-relaxed text-foreground pr-14">
              {item.t3_summary}
            </p>
          ) : item.t1_tldr ? (
            <p className="font-serif text-[15px] leading-relaxed text-foreground pr-14">
              {item.t1_tldr}
            </p>
          ) : item.t2_summary ? (
            <p className="font-serif text-[15px] leading-relaxed text-foreground pr-14">
              {item.t2_summary}
            </p>
          ) : (
            <p className="font-serif text-[15px] leading-relaxed text-muted-foreground italic line-clamp-4 mt-6">
              {item.abstract}
            </p>
          )}
        </div>

        {/* 2. Title and Authors */}
        <div className="mb-4 border-l-2 border-muted pl-3">
          <h3 className={`font-semibold text-sm leading-snug mb-1 text-muted-foreground group-hover:text-foreground transition-colors cursor-pointer ${expandedAuthors ? '' : 'line-clamp-2'}`} onClick={() => setExpandedAuthors(!expandedAuthors)} title="Click to expand/collapse">
            {item.title}
          </h3>
          <p className="text-xs text-muted-foreground/80 leading-relaxed flex flex-wrap gap-x-1.5 gap-y-1 items-center">
            {item.author_details && item.author_details.length > 0 ? (
              <>
                {(expandedAuthors ? item.author_details : item.author_details.slice(0, 8)).map((author: { authorId?: string; orcid?: string; name: string }, idx: number, arr: any[]) => {
                const s2Id = author.authorId ? `AUTHOR_ID:${author.authorId}` : (author.orcid ? `ORCID:${author.orcid}` : null);
                const followRecord = s2Id ? follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value === s2Id) : null;
                const isFollowed = !!followRecord;
                return (
                  <span key={idx} className="inline-flex items-center gap-0.5">
                    {s2Id ? (
                      <>
                        <NavLink 
                          to={`/author/${s2Id}`}
                          className={`hover:underline cursor-pointer transition-colors ${isFollowed ? 'text-primary font-semibold' : ''}`}
                          title="View Author Dashboard"
                        >
                          {author.name}
                        </NavLink>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            if (isFollowed) {
                              deleteFollow.mutate(followRecord.id)
                            } else {
                              createFollow.mutate({ entity_type: 'author', entity_value: s2Id, display_name: author.name, boost_value: 0.15 })
                            }
                          }}
                          className={`flex items-center justify-center w-3.5 h-3.5 rounded-full text-[8px] font-bold transition-colors ${isFollowed ? 'bg-primary text-primary-foreground hover:bg-destructive hover:text-destructive-foreground' : 'bg-muted text-muted-foreground hover:bg-primary hover:text-primary-foreground'}`}
                          title={isFollowed ? "Unfollow Author" : "Follow Author"}
                        >
                          {isFollowed ? '✓' : '+'}
                        </button>
                      </>
                    ) : (
                      <>
                        <span className={isFollowed ? 'text-primary font-semibold' : ''}>{author.name}</span>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            const followByName = follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value.toLowerCase() === author.name.toLowerCase());
                            if (followByName) {
                              deleteFollow.mutate(followByName.id)
                            } else {
                              createFollow.mutate({ entity_type: 'author', entity_value: author.name, boost_value: 0.15 })
                            }
                          }}
                          className={`flex items-center justify-center w-3.5 h-3.5 rounded-full text-[8px] font-bold transition-colors ${follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value.toLowerCase() === author.name.toLowerCase()) ? 'bg-primary text-primary-foreground hover:bg-destructive hover:text-destructive-foreground' : 'bg-muted text-muted-foreground hover:bg-primary hover:text-primary-foreground'}`}
                          title={follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value.toLowerCase() === author.name.toLowerCase()) ? "Unfollow Author" : "Follow Author"}
                        >
                          {follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value.toLowerCase() === author.name.toLowerCase()) ? '✓' : '+'}
                        </button>
                      </>
                    )}
                    {idx < arr.length - 1 && <span className="text-muted-foreground">,</span>}
                  </span>
                )
                })}
                {!expandedAuthors && isLongAuthorList && (
                  <button onClick={() => setExpandedAuthors(true)} className="text-primary hover:underline font-medium text-[10px] ml-1 bg-primary/10 px-1.5 py-0.5 rounded">
                    + {item.author_details.length - 8} more
                  </button>
                )}
              </>
            ) : item.authors && item.authors.length > 0 ? (
              <>
                {(expandedAuthors ? item.authors : item.authors.slice(0, 8)).map((author: string, idx: number, arr: string[]) => {
                const followRecord = follows?.find((f: Follow) => f.entity_type === 'author' && f.entity_value.toLowerCase() === author.toLowerCase())
                const isFollowed = !!followRecord
                return (
                  <span key={idx} className="inline-flex items-center gap-0.5">
                    <span className={`transition-colors ${isFollowed ? 'text-primary font-semibold' : ''}`}>
                      {author}
                    </span>
                    <button 
                      onClick={(e) => { 
                        e.preventDefault(); 
                        if (isFollowed) {
                          deleteFollow.mutate(followRecord.id)
                        } else {
                          createFollow.mutate({ entity_type: 'author', entity_value: author, boost_value: 0.15 })
                        }
                      }}
                      className={`flex items-center justify-center w-3.5 h-3.5 rounded-full text-[8px] font-bold transition-colors ${isFollowed ? 'bg-primary text-primary-foreground hover:bg-destructive hover:text-destructive-foreground' : 'bg-muted text-muted-foreground hover:bg-primary hover:text-primary-foreground'}`}
                      title={isFollowed ? "Unfollow Author" : "Follow Author"}
                    >
                      {isFollowed ? '✓' : '+'}
                    </button>
                    {idx < arr.length - 1 && <span className="text-muted-foreground">,</span>}
                  </span>
                )
                })}
                {!expandedAuthors && isLongAuthorList && (
                  <button onClick={() => setExpandedAuthors(true)} className="text-primary hover:underline font-medium text-[10px] ml-1 bg-primary/10 px-1.5 py-0.5 rounded">
                    + {item.authors.length - 8} more
                  </button>
                )}
              </>
            ) : null}
          </p>
        </div>
        
        {/* Extracted Tools Tags */}
        {item.tools && item.tools.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3 mb-2">
            {item.tools.map((tool: string, idx: number) => (
              <span key={idx} className="px-2 py-0.5 bg-primary/10 text-primary rounded text-[10px] font-semibold border border-primary/20">
                {tool}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-between items-stretch mt-2 pt-3 border-t border-border/50">
        <div className="flex flex-col justify-center text-[11px] font-medium tracking-wide uppercase text-muted-foreground gap-1">
          <span>{new Date(item.published_at).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'})}</span>
          <a 
            href={item.doi ? `https://doi.org/${item.doi}` : item.url} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="text-foreground/70 hover:text-primary hover:underline line-clamp-1 pr-2" 
            title={item.venue || item.source}
          >
            {item.venue || item.source}
          </a>
        </div>
        <div className="flex items-stretch gap-2 shrink-0">
          {item.is_open_access && item.open_access_pdf_url && (
            <a href={item.open_access_pdf_url} target="_blank" rel="noopener noreferrer" className="bg-red-50 text-red-600 hover:bg-red-100 px-3 flex items-center justify-center rounded transition-colors font-bold text-[11px] uppercase tracking-wider">
              PDF 📄
            </a>
          )}
          <a href={item.doi ? `https://doi.org/${item.doi}` : item.url} target="_blank" rel="noopener noreferrer" className="bg-primary/10 text-primary hover:bg-primary/20 px-4 flex items-center justify-center rounded transition-colors font-bold text-[11px] uppercase tracking-wider">
            Read Article ↗
          </a>
        </div>
      </div>
    </div>
  )
}
