/**
 * SCRUM-81 — Toast notification UI.
 * Renders a stack of toasts in the bottom-right corner.
 * Use with useToast() hook.
 *
 * <ToastContainer toasts={toasts} onDismiss={dismiss} />
 */

const ICONS = {
  success: 'check_circle',
  error:   'error',
  warning: 'warning',
  info:    'info',
}

const COLORS = {
  success: { bg: 'rgba(16,185,129,0.15)',  border: 'rgba(16,185,129,0.3)',  icon: '#6ee7b7' },
  error:   { bg: 'rgba(186,26,26,0.15)',   border: 'rgba(186,26,26,0.3)',   icon: '#fca5a5' },
  warning: { bg: 'rgba(245,158,11,0.15)',  border: 'rgba(245,158,11,0.3)',  icon: '#fcd34d' },
  info:    { bg: 'rgba(59,130,246,0.15)',  border: 'rgba(59,130,246,0.3)',  icon: '#93c5fd' },
}

function ToastItem({ toast, onDismiss }) {
  const c = COLORS[toast.type] ?? COLORS.info
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '0.85rem 1rem',
        borderRadius: '0.85rem',
        background: c.bg,
        border: `1px solid ${c.border}`,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
        minWidth: '280px',
        maxWidth: '380px',
        animation: 'toastIn 0.25s ease',
      }}
    >
      <span className="material-icons-round" style={{ fontSize: '1.1rem', color: c.icon, flexShrink: 0, marginTop: '1px' }}>
        {ICONS[toast.type] ?? 'info'}
      </span>
      <p style={{ flex: 1, fontFamily: 'Inter, sans-serif', fontSize: '0.84rem', color: 'white', lineHeight: 1.5 }}>
        {toast.message}
      </p>
      <button
        onClick={() => onDismiss(toast.id)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'rgba(255,255,255,0.4)', lineHeight: 1 }}
      >
        <span className="material-icons-round" style={{ fontSize: '1rem' }}>close</span>
      </button>
    </div>
  )
}

export function ToastContainer({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        right: '1.5rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
        zIndex: 9999,
      }}
    >
      {toasts.map(t => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
