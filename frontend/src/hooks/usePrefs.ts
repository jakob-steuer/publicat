import { useCallback, useEffect, useState } from 'react'
import type { InboxSort } from '../types'

/** Per-browser triage preferences, persisted in localStorage. */
export interface Prefs {
  minScore: number;
  showPreprints: boolean;
  showRated: boolean;
  sort: InboxSort;
  days: number;
  dark: boolean;
  autoAdvance: boolean;
}

const KEY = 'publicat.prefs.v1'

const defaults: Prefs = {
  minScore: 0.5,
  showPreprints: true,
  showRated: false,
  sort: 'score',
  days: 56,
  dark: typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)').matches : false,
  autoAdvance: true,
}

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...defaults, ...JSON.parse(raw) }
    // migrate the old scattered keys once
    const legacyRated = localStorage.getItem('publikater_show_rated')
    const legacyPre = localStorage.getItem('publikater_show_preprints')
    const legacyTheme = localStorage.getItem('theme')
    return {
      ...defaults,
      showRated: legacyRated !== null ? legacyRated === 'true' : defaults.showRated,
      showPreprints: legacyPre !== null ? legacyPre === 'true' : defaults.showPreprints,
      dark: legacyTheme ? legacyTheme === 'dark' : defaults.dark,
    }
  } catch {
    return defaults
  }
}

export function usePrefs() {
  const [prefs, setPrefs] = useState<Prefs>(load)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(prefs)) } catch { /* private mode */ }
    document.documentElement.classList.toggle('dark', prefs.dark)
  }, [prefs])

  const update = useCallback((patch: Partial<Prefs>) => setPrefs(p => ({ ...p, ...patch })), [])
  return { prefs, update }
}
