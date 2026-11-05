import { useState } from 'react'
import { scoreTone, splitReason } from '../../lib/format'

export function ReasonList({ reasons, className = '' }: { reasons: string[]; className?: string }) {
  if (!reasons.length) return null
  return (
    <div className={`text-xs space-y-1 ${className}`}>
      <div className="font-semibold text-foreground">{reasons[0]}</div>
      {reasons.slice(1).map((r, i) => {
        const { label, value } = splitReason(r)
        const negative = value.startsWith('-')
        return (
          <div key={i} className={`flex justify-between gap-3 ${negative ? 'text-red-600 dark:text-red-400' : 'text-foreground/80'}`}>
            <span>{label}</span>
            <span className="font-mono shrink-0">{value}</span>
          </div>
        )
      })}
    </div>
  )
}

interface Props {
  score: number;
  reasons?: string[];
  size?: 'sm' | 'md';
}

export function ScoreChip({ score, reasons = [], size = 'sm' }: Props) {
  const [open, setOpen] = useState(false)
  const dim = size === 'sm' ? 'w-9 h-6 text-[11px]' : 'w-12 h-8 text-sm'
  return (
    <div className="relative shrink-0" onClick={e => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        title={reasons.length ? 'Why this score?' : `Relevance ${(score * 100).toFixed(0)}%`}
        className={`${dim} rounded-md border font-bold flex items-center justify-center tabular-nums ${scoreTone(score)}`}
      >
        {(Math.min(score, 1) * 100).toFixed(0)}
      </button>
      {open && reasons.length > 0 && (
        <div className="absolute left-0 top-full mt-1 z-40 w-80 bg-popover text-popover-foreground border border-border rounded-md shadow-xl p-3" onMouseLeave={() => setOpen(false)}>
          <ReasonList reasons={reasons} />
        </div>
      )}
    </div>
  )
}
