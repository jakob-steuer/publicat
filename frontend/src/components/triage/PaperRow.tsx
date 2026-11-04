import { memo } from 'react'
import { FileText } from 'lucide-react'
import type { Item, Vote } from '../../types'
import { ScoreChip } from './ScoreChip'
import { VoteButtons } from './VoteButtons'
import { authorLine, formatDate } from '../../lib/format'

interface Props {
  item: Item;
  focused: boolean;
  open: boolean;
  selected: boolean;
  showTopic: boolean;
  onFocus: () => void;
  onOpen: () => void;
  onVote: (v: Vote) => void;
  onToggleSelect: () => void;
}

function PaperRowInner({ item, focused, open, selected, showTopic, onFocus, onOpen, onVote, onToggleSelect }: Props) {
  const voted = item.user_vote !== null && item.user_vote !== undefined
  const summary = item.t3_summary || item.t2_summary || item.t1_tldr
  return (
    <div
      data-row-id={item.id}
      onClick={() => { onFocus(); onOpen() }}
      onMouseEnter={onFocus}
      className={`group grid grid-cols-[auto_auto_minmax(0,1fr)_auto] items-start gap-3 px-3 py-2.5 border-b border-border/60 cursor-pointer transition-colors ${
        open ? 'bg-primary/10' : focused ? 'bg-muted/60' : 'hover:bg-muted/40'
      } ${voted ? 'opacity-60' : ''}`}
      role="option"
      aria-selected={open}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggleSelect}
        onClick={e => e.stopPropagation()}
        className="mt-1 w-4 h-4 accent-primary cursor-pointer"
        aria-label="Select paper"
      />
      <div className="mt-0.5">
        {item.score !== undefined && item.score !== null && <ScoreChip score={item.score} reasons={item.reasons} />}
      </div>
      <div className="min-w-0">
        <div className="font-medium text-[15px] leading-snug text-foreground line-clamp-2">{item.title}</div>
        {summary && <div className="text-[13px] text-muted-foreground leading-snug line-clamp-2 mt-0.5 font-serif">{summary}</div>}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground mt-1">
          <span className="truncate max-w-[40ch]">{authorLine(item)}</span>
          {item.venue && <span className="truncate max-w-[28ch]">· {item.venue}</span>}
          <span>· {formatDate(item.published_at)}</span>
          {item.is_open_access && item.open_access_pdf_url && <span className="inline-flex items-center gap-0.5 text-red-600/80"><FileText size={11} /> PDF</span>}
          {showTopic && item.topic_name && (
            <span className="px-1.5 py-px rounded bg-primary/10 text-primary border border-primary/20 truncate max-w-[24ch]" title={`Votes train "${item.topic_name}"`}>{item.topic_name}</span>
          )}
        </div>
      </div>
      <VoteButtons
        value={(item.user_vote ?? undefined) as Vote | undefined}
        onVote={onVote}
        className={`mt-0.5 transition-opacity ${voted || focused || open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
      />
    </div>
  )
}

export const PaperRow = memo(PaperRowInner)
