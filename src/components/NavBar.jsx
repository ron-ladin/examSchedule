/**
 * SCRUM-92 — Shared top navigation bar used by ResultsView and DetailedCalendar.
 *
 * Props:
 *   currentPath   string         — active route path (highlights nav item)
 *   rightContent  ReactNode      — slot rendered on the right side; defaults to Sign Out link
 */
import { Link } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'

const NAV_ITEMS = [
  { label: 'Dashboard',       path: '/dashboard', icon: 'dashboard'        },
  { label: 'Schedules',       path: '/results',   icon: 'calendar_today'   },
  { label: 'Conflict Solver', path: '/calendar',  icon: 'auto_fix_high'    },
]

export default function NavBar({ currentPath, rightContent }) {
  return (
    <header
      style={{
        borderBottom: '1px solid var(--outline-variant)',
        background: 'var(--surface-container-lowest)',
        padding: '0 2rem',
        height: '64px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '7px',
            background: 'var(--gradient-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span className="material-symbols-outlined" style={{ color: 'white', fontSize: '0.9rem' }}>
            auto_fix_high
          </span>
        </div>
        <span
          style={{
            fontFamily: 'Sora, sans-serif',
            fontWeight: 700,
            fontSize: '1rem',
            color: 'var(--on-surface)',
            letterSpacing: '-0.02em',
          }}
        >
          Syncademic
        </span>
      </div>

      {/* Nav links */}
      <nav style={{ display: 'flex', gap: '0.25rem' }}>
        {NAV_ITEMS.map(item => (
          <Link
            key={item.label}
            to={item.path}
            className={`sidebar-item${currentPath === item.path ? ' active' : ''}`}
            style={{ padding: '0.5rem 0.875rem', borderRadius: '9999px' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>
              {item.icon}
            </span>
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Right slot */}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <ThemeToggle />
        {rightContent ?? (
          <Link
            to="/"
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8rem',
              color: 'var(--outline)',
              textDecoration: 'none',
            }}
          >
            Sign Out
          </Link>
        )}
      </div>
    </header>
  )
}
