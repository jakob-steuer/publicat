import { Star, ThumbsUp, Minus, ThumbsDown } from 'lucide-react'
import type { Vote } from '../../types'

interface Props {
  value: Vote | undefined;
  onVote: (v: Vote) => void;
  size?: 'sm' | 'md';
  className?: string;
}

const BUTTONS: Array<{ vote: Vote; Icon: typeof Star; title: string; active: string; hover: string }> = [
  { vote: 2, Icon: Star, title: 'Star · save (s)', active: 'bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/50 dark:text-yellow-300 dark:border-yellow-700', hover: 'hover:text-yellow-500' },
  { vote: 1, Icon: ThumbsUp, title: 'Upvote · relevant (u)', active: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/50 dark:text-green-300 dark:border-green-700', hover: 'hover:text-green-500' },
  { vote: 0, Icon: Minus, title: 'Neutral · mark read (n)', active: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/50 dark:text-blue-300 dark:border-blue-700', hover: 'hover:text-blue-500' },
  { vote: -1, Icon: ThumbsDown, title: 'Downvote · discard (d)', active: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/50 dark:text-red-300 dark:border-red-700', hover: 'hover:text-red-500' },
]

export function VoteButtons({ value, onVote, size = 'sm', className = '' }: Props) {
  const dim = size === 'sm' ? 'w-7 h-7' : 'w-9 h-9'
  const icon = size === 'sm' ? 14 : 18
  return (
    <div className={`flex items-center gap-1 ${className}`} onClick={e => e.stopPropagation()}>
      {BUTTONS.map(({ vote, Icon, title, active, hover }) => {
        const isActive = value === vote
        return (
          <button
            key={String(vote)}
            type="button"
            onClick={() => onVote(vote)}
            title={title}
            aria-pressed={isActive}
            className={`${dim} rounded-full border flex items-center justify-center transition-transform hover:scale-110 ${
              isActive ? active : `bg-background/60 text-muted-foreground border-border/60 ${hover}`
            }`}
          >
            <Icon size={icon} className={isActive && vote !== 0 ? 'fill-current' : ''} />
          </button>
        )
      })}
    </div>
  )
}
