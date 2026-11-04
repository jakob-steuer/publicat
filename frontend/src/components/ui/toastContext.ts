import { createContext } from 'react'

export type ToastKind = 'info' | 'success' | 'error'

export interface ToastOptions {
  kind?: ToastKind;
  /** ms before auto-dismiss; 0 keeps it until closed */
  duration?: number;
  action?: { label: string; onClick: () => void };
}

export interface ToastApi {
  toast: (message: string, options?: ToastOptions) => void;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastApi | null>(null)
