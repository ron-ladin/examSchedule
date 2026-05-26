/**
 * ThemeToggle — sun/moon button that switches light ↔ dark mode.
 * Uses useTheme() which writes data-theme="dark|light" to <html>.
 *
 * Props:
 *   size   number  icon font-size in rem (default 1.1)
 *   color  string  icon colour override (default var(--on-surface-variant))
 */
import { useTheme } from '../hooks/useTheme'

export default function ThemeToggle({ size = 1.1, color }) {
  const { isDark, toggle } = useTheme()

  return (
    <button
      onClick={toggle}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      style={{
        background: 'none',
        border: '1.5px solid var(--outline-variant)',
        borderRadius: '50%',
        width:  '2rem',
        height: '2rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'border-color 0.15s, background 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background    = 'var(--surface-container)'
        e.currentTarget.style.borderColor   = 'var(--primary)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background    = 'none'
        e.currentTarget.style.borderColor   = 'var(--outline-variant)'
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: `${size}rem`,
          color: color ?? 'var(--on-surface-variant)',
          transition: 'color 0.15s',
          lineHeight: 1,
        }}
      >
        {isDark ? 'light_mode' : 'dark_mode'}
      </span>
    </button>
  )
}
