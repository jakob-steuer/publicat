import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Item, Topic, Vote } from '../../types'
import { PaperRow } from './PaperRow'
import { ReadingPane } from './ReadingPane'
import { ShortcutHelp } from './ShortcutHelp'
import { BulkBar } from './BulkBar'
import { useVote } from '../../hooks/useVote'

interface Props {
  items: Item[];
  topics: Topic[];
  showTopic: boolean;
  autoAdvance: boolean;
  /** Called when focus moves past the last loaded row (load the next page). */
  onReachEnd?: () => void;
  emptyState: React.ReactNode;
  header?: React.ReactNode;
  /** Rendered after the last row inside the scroll area (e.g. a load-more button). */
  footer?: React.ReactNode;
  searchRef?: React.RefObject<HTMLInputElement | null>;
  bulkVotes?: boolean;
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/**
 * The triage list: keyboard-driven, with a reading pane and bulk selection.
 * Rows are not removed when voted (that would make the list jump); they dim.
 */
export function PaperList({ items, topics, showTopic, autoAdvance, onReachEnd, emptyState, header, footer, searchRef, bulkVotes = true }: Props) {
  const { cast, undo } = useVote()
  const [focusIdx, setFocusIdx] = useState(0)
  const [openId, setOpenId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [showHelp, setShowHelp] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  const safeIdx = Math.min(focusIdx, Math.max(items.length - 1, 0))
  const focused = items[safeIdx]
  const openItem = useMemo(() => items.find(i => i.id === openId) ?? null, [items, openId])

  useEffect(() => {
    const row = listRef.current?.querySelector<HTMLElement>(`[data-row-id="${focused?.id}"]`)
    row?.scrollIntoView({ block: 'nearest' })
  }, [focused?.id])

  const move = useCallback((delta: number) => {
    setFocusIdx(i => {
      const next = Math.min(Math.max(i + delta, 0), Math.max(items.length - 1, 0))
      if (next >= items.length - 3) onReachEnd?.()
      return next
    })
  }, [items.length, onReachEnd])

  const voteOn = useCallback((item: Item, v: Vote, topicId?: string | null, advance = autoAdvance) => {
    cast(item, v, topicId)
    if (advance && openId === item.id) {
      const idx = items.findIndex(i => i.id === item.id)
      const next = items[idx + 1]
      if (next) { setOpenId(next.id); setFocusIdx(idx + 1) }
    } else if (advance && focused?.id === item.id) {
      move(1)
    }
  }, [cast, autoAdvance, openId, items, focused?.id, move])

  const toggleSelect = useCallback((id: string) => {
    setSelected(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (isTypingTarget(e.target)) {
        if (e.key === 'Escape') (e.target as HTMLElement).blur()
        return
      }
      const key = e.key
      if (key === '?') { e.preventDefault(); setShowHelp(h => !h); return }
      if (key === 'Escape') { if (showHelp) setShowHelp(false); else setOpenId(null); return }
      if (key === '/') { e.preventDefault(); searchRef?.current?.focus(); return }
      if (key === 'j' || key === 'ArrowDown') { e.preventDefault(); move(1); if (openId) setOpenId(items[Math.min(safeIdx + 1, items.length - 1)]?.id ?? null); return }
      if (key === 'k' || key === 'ArrowUp') { e.preventDefault(); move(-1); if (openId) setOpenId(items[Math.max(safeIdx - 1, 0)]?.id ?? null); return }
      if (!focused) return
      if (key === 'Enter' || key === ' ') { e.preventDefault(); setOpenId(o => (o === focused.id ? null : focused.id)); return }
      if (key === 's') { voteOn(focused, 2); return }
      if (key === 'u') { voteOn(focused, 1); return }
      if (key === 'n') { voteOn(focused, 0); return }
      if (key === 'd') { voteOn(focused, -1); return }
      if (key === 'z') { undo(); return }
      if (key === 'x') { toggleSelect(focused.id); return }
      if (key === 'o') { window.open(focused.doi ? `https://doi.org/${focused.doi}` : focused.url, '_blank', 'noopener'); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focused, safeIdx, items, move, openId, showHelp, undo, voteOn, toggleSelect, searchRef])

  const selectAllVisible = () => {
    const ids = items.map(i => i.id)
    setSelected(prev => (ids.every(id => prev.has(id)) ? new Set() : new Set(ids)))
  }
  const bulkVote = (v: Vote) => {
    items.filter(i => selected.has(i.id)).forEach(i => cast(i, v, undefined, { silent: true }))
    setSelected(new Set())
  }

  return (
    <div className={`grid h-full min-h-0 ${openItem ? 'md:grid-cols-[minmax(0,1fr)_minmax(360px,42%)]' : 'grid-cols-1'}`}>
      <div className="flex flex-col min-h-0 min-w-0">
        {header}
        <div ref={listRef} className="flex-1 overflow-y-auto" role="listbox" aria-label="Papers">
          {items.length === 0 ? (
            emptyState
          ) : (
            <>
              <div className="flex items-center justify-between px-3 py-1.5 text-[11px] text-muted-foreground border-b border-border/60 bg-muted/20 sticky top-0 z-10">
                <button onClick={selectAllVisible} className="hover:text-foreground">{items.every(i => selected.has(i.id)) && items.length > 0 ? 'Deselect all' : 'Select all'}</button>
                <button onClick={() => setShowHelp(true)} className="hover:text-foreground">Keyboard: j k s u n d z · <kbd className="font-mono">?</kbd></button>
              </div>
              {items.map((item, idx) => (
                <PaperRow
                  key={item.id}
                  item={item}
                  focused={idx === safeIdx}
                  open={item.id === openId}
                  selected={selected.has(item.id)}
                  showTopic={showTopic}
                  onFocus={() => setFocusIdx(idx)}
                  onOpen={() => setOpenId(o => (o === item.id ? null : item.id))}
                  onVote={v => voteOn(item, v, undefined, false)}
                  onToggleSelect={() => toggleSelect(item.id)}
                />
              ))}
              {footer}
            </>
          )}
        </div>
      </div>

      {openItem && (
        <div className="fixed inset-0 z-40 md:static md:z-auto md:h-full md:min-h-0">
          <ReadingPane item={openItem} topics={topics} onClose={() => setOpenId(null)} onVote={(v, topicId) => voteOn(openItem, v, topicId)} />
        </div>
      )}

      <BulkBar count={selected.size} ids={[...selected]} onVote={bulkVote} onClear={() => setSelected(new Set())} showVotes={bulkVotes} />
      {showHelp && <ShortcutHelp onClose={() => setShowHelp(false)} />}
    </div>
  )
}
