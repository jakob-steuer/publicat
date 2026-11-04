import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { ToastContext, type ToastOptions } from './toastContext'

interface ToastItem extends ToastOptions {
  id: number;
  message: string;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => setToasts(ts => ts.filter(t => t.id !== id)), [])

  const toast = useCallback((message: string, options: ToastOptions = {}) => {
    const id = nextId.current++
    const item: ToastItem = { id, message, kind: options.kind ?? 'info', duration: options.duration ?? (options.action ? 6000 : 3500), action: options.action }
    setToasts(ts => [...ts.slice(-3), item])
    if (item.duration && item.duration > 0) {
      setTimeout(() => dismiss(id), item.duration)
    }
  }, [dismiss])

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 left-4 md:left-[17.5rem] z-[200] flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))]" role="status" aria-live="polite">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-sm shadow-lg bg-card text-card-foreground animate-in slide-in-from-bottom-2 ${
              t.kind === 'error' ? 'border-red-400/60' : t.kind === 'success' ? 'border-emerald-400/60' : 'border-border'
            }`}
          >
            <span className="flex-1 leading-snug">{t.message}</span>
            {t.action && (
              <button
                onClick={() => { t.action?.onClick(); dismiss(t.id) }}
                className="font-semibold text-primary hover:underline shrink-0"
              >
                {t.action.label}
              </button>
            )}
            <button onClick={() => dismiss(t.id)} className="text-muted-foreground hover:text-foreground shrink-0" aria-label="Dismiss">×</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
