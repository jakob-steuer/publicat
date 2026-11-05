import type { Item } from '../types'

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function authorLine(item: Item, max = 3): string {
  const names = item.author_details?.map(a => a.name) ?? item.authors ?? []
  if (names.length <= max) return names.join(', ')
  return `${names.slice(0, max).join(', ')} +${names.length - max}`
}

export function scoreTone(score: number): string {
  if (score >= 0.9) return 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200 dark:border-emerald-700'
  if (score >= 0.75) return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/40 dark:text-green-200 dark:border-green-700'
  if (score >= 0.6) return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/40 dark:text-yellow-200 dark:border-yellow-700'
  if (score >= 0.4) return 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/40 dark:text-orange-200 dark:border-orange-700'
  return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/40 dark:text-red-200 dark:border-red-700'
}

/** Splits "Keyword in title: 'x' (+0.6)" into label and signed contribution. */
export function splitReason(r: string): { label: string; value: string } {
  const m = r.match(/^(.*?)\s*\(([+-][\d.]+)\)$/)
  return m ? { label: m[1], value: m[2] } : { label: r, value: '' }
}
