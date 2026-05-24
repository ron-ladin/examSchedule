import { useState, useCallback, useRef } from 'react'

let _nextId = 1

/**
 * SCRUM-81 — Toast notification hook.
 * Returns { toasts, toast } where toast(message, type, duration) queues a notification.
 * Type: 'success' | 'error' | 'info' | 'warning'
 */
export function useToast() {
  const [toasts, setToasts] = useState([])
  const timers = useRef({})

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id])
    delete timers.current[id]
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((message, type = 'info', duration = 4000) => {
    const id = _nextId++
    setToasts(prev => [...prev, { id, message, type }])
    timers.current[id] = setTimeout(() => dismiss(id), duration)
    return id
  }, [dismiss])

  return { toasts, toast, dismiss }
}
