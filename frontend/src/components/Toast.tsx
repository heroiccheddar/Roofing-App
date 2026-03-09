/**
 * Toast — lightweight notification toasts with auto-dismiss.
 *
 * Usage:
 *   import { showToast } from './Toast'
 *   showToast('Pin saved')
 *   showToast('Moved to Interested', 'success')
 *   showToast('Failed to save', 'error')
 *
 * Render <ToastContainer /> once at the app root.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { create } from 'zustand'

// ===== Store =====

type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

interface ToastStore {
  toasts: ToastItem[]
  add: (message: string, type: ToastType) => void
  remove: (id: number) => void
}

let nextId = 1

const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  add: (message, type) => {
    const id = nextId++
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
  },
  remove: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },
}))

/** Show a toast notification. Can be called from anywhere — no hooks needed. */
export function showToast(message: string, type: ToastType = 'success') {
  useToastStore.getState().add(message, type)
}

// ===== Components =====

function ToastItem({ toast }: { toast: ToastItem }) {
  const remove = useToastStore((s) => s.remove)
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    // Fade in
    requestAnimationFrame(() => setVisible(true))
    // Auto-dismiss after 2.5s
    timerRef.current = setTimeout(() => {
      setVisible(false)
      setTimeout(() => remove(toast.id), 250)
    }, 2500)
    return () => clearTimeout(timerRef.current)
  }, [toast.id, remove])

  const handleDismiss = useCallback(() => {
    clearTimeout(timerRef.current)
    setVisible(false)
    setTimeout(() => remove(toast.id), 250)
  }, [toast.id, remove])

  const bgColor =
    toast.type === 'error' ? '#ef4444'
    : toast.type === 'info' ? '#3b82f6'
    : '#22c55e'

  return (
    <div
      onClick={handleDismiss}
      style={{
        background: bgColor,
        color: '#fff',
        padding: '10px 18px',
        borderRadius: 8,
        fontSize: 13,
        fontWeight: 600,
        fontFamily: 'system-ui, -apple-system, sans-serif',
        boxShadow: '0 4px 14px rgba(0,0,0,0.25)',
        cursor: 'pointer',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(8px)',
        transition: 'opacity 0.25s, transform 0.25s',
        maxWidth: 340,
        lineHeight: '1.4',
        pointerEvents: 'auto',
      }}
    >
      {toast.message}
    </div>
  )
}

/** Render once at the app root. */
export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)

  if (toasts.length === 0) return null

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        pointerEvents: 'none',
      }}
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  )
}
