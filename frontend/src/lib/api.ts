/**
 * Where the backend lives.
 *
 * In production the React build is served by the FastAPI process itself, so
 * every request is same-origin and the base is empty. Only the Vite dev
 * server (port 5173) needs to point at the backend explicitly. Set
 * VITE_API_URL to override either (e.g. a phone talking to a laptop).
 */
export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (import.meta.env.DEV ? 'http://localhost:8001' : '')

/** Absolute URL for links that leave the app (Zotero, downloads). */
export function absoluteApiUrl(path: string): string {
  return `${API_BASE || window.location.origin}${path}`
}
