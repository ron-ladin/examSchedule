import { useNavigate, useLocation } from 'react-router-dom'

/* ── Icon ──────────────────────────────────────────────────────── */
export function Icon({ name, className = '', fill = false, style = {} }) {
  return (
    <span
      className={`material-symbols-outlined ${fill ? 'ms-fill' : ''} ${className}`}
      style={style}
    >
      {name}
    </span>
  )
}

/* ── AmbientOrbs ───────────────────────────────────────────────── */
export function AmbientOrbs({ variant = 'default' }) {
  const presets = {
    default: [
      { cls: 'orb-blue drift-a',   style: { width: 600, height: 600, top: -180, left: -120 } },
      { cls: 'orb-purple drift-b', style: { width: 680, height: 680, bottom: -220, right: -160 } },
      { cls: 'orb-cyan drift-c',   style: { width: 420, height: 420, top: '38%', left: '42%' } },
    ],
    auth: [
      { cls: 'orb-blue drift-a',   style: { width: 600, height: 600, top: -120, left: -100 } },
      { cls: 'orb-purple drift-b', style: { width: 700, height: 700, bottom: -180, right: -120 } },
    ],
    workspace: [
      { cls: 'orb-blue drift-a',   style: { width: 520, height: 520, top: -180, left: -80 } },
      { cls: 'orb-purple drift-b', style: { width: 560, height: 560, bottom: -200, right: -100 } },
      { cls: 'orb-cyan drift-c',   style: { width: 360, height: 360, top: '60%', left: '55%' } },
    ],
    processing: [
      { cls: 'orb-blue drift-a',   style: { width: 520, height: 520, top: -160, left: -80 } },
      { cls: 'orb-purple drift-b', style: { width: 460, height: 460, bottom: -120, right: -60 } },
      { cls: 'orb-cyan drift-c',   style: { width: 300, height: 300, top: '45%', left: '40%' } },
    ],
  }
  const orbs = presets[variant] || presets.default
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 0 }}>
      {orbs.map((o, i) => (
        <div key={i} className={`orb ${o.cls}`} style={o.style} />
      ))}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(218,226,253,1) 1px, transparent 1px), linear-gradient(90deg, rgba(218,226,253,1) 1px, transparent 1px)',
          backgroundSize: '80px 80px',
          maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        }}
      />
    </div>
  )
}

/* ── BrandMark ─────────────────────────────────────────────────── */
export function BrandMark({ size = 40, withWord = true, subtitle = null }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="rounded-xl flex items-center justify-center shadow-lg relative"
        style={{
          width: size,
          height: size,
          background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
          boxShadow: '0 8px 24px -8px rgba(139,92,246,0.6), inset 0 1px 0 rgba(255,255,255,0.3)',
          flexShrink: 0,
        }}
      >
        <Icon name="auto_fix_high" fill className="text-white text-[20px]" />
        <div className="absolute inset-0 rounded-xl ring-rim" />
      </div>
      {withWord && (
        <div className="leading-tight">
          <h1 className="font-extrabold tracking-tight grad-text-cool" style={{ fontSize: 30 }}>
            Syncademic
          </h1>
          {subtitle && (
            <p className="text-[9.5px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold">
              {subtitle}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Chip ──────────────────────────────────────────────────────── */
export function Chip({ children, tone = 'primary', className = '' }) {
  const tones = {
    primary:   { bg: 'rgba(173,198,255,0.10)', bd: 'rgba(173,198,255,0.22)', fg: '#adc6ff' },
    secondary: { bg: 'rgba(208,188,255,0.10)', bd: 'rgba(208,188,255,0.22)', fg: '#d0bcff' },
    tertiary:  { bg: 'rgba(255,183,134,0.10)', bd: 'rgba(255,183,134,0.22)', fg: '#ffb786' },
    error:     { bg: 'rgba(255,180,171,0.10)', bd: 'rgba(255,180,171,0.22)', fg: '#ffb4ab' },
    neutral:   { bg: 'rgba(255,255,255,0.05)', bd: 'rgba(255,255,255,0.10)', fg: '#dae2fd' },
  }
  const t = tones[tone] || tones.primary
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.16em] ${className}`}
      style={{ background: t.bg, border: `1px solid ${t.bd}`, color: t.fg }}
    >
      {children}
    </span>
  )
}

/* ── GradButton ────────────────────────────────────────────────── */
export function GradButton({ children, onClick, type = 'button', icon = null, iconAfter = null, className = '', size = 'md', disabled = false }) {
  const sizes = {
    sm: 'px-5 py-2.5 text-[12px]',
    md: 'px-7 py-3.5 text-[13px]',
    lg: 'px-10 py-4 text-[14px]',
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn-grad inline-flex items-center justify-center gap-2 rounded-full font-semibold uppercase tracking-[0.08em] ${sizes[size]} ${className}`}
    >
      {icon && <Icon name={icon} className="text-[18px]" />}
      <span>{children}</span>
      {iconAfter && <Icon name={iconAfter} className="text-[18px]" />}
    </button>
  )
}

/* ── GhostButton ───────────────────────────────────────────────── */
export function GhostButton({ children, onClick, icon = null, iconAfter = null, className = '', size = 'md' }) {
  const sizes = {
    sm: 'px-5 py-2.5 text-[12px]',
    md: 'px-6 py-3 text-[13px]',
    lg: 'px-8 py-4 text-[14px]',
  }
  return (
    <button
      onClick={onClick}
      className={`btn-ghost glass inline-flex items-center justify-center gap-2 rounded-full font-semibold uppercase tracking-[0.08em] text-on-surface ${sizes[size]} ${className}`}
    >
      {icon && <Icon name={icon} className="text-[18px]" />}
      <span>{children}</span>
      {iconAfter && <Icon name={iconAfter} className="text-[18px]" />}
    </button>
  )
}

/* ── Sidebar nav definition ────────────────────────────────────── */
const NAV = [
  { key: 'dashboard',  label: 'Dashboard',      icon: 'dashboard',     path: '/dashboard' },
  { key: 'results',    label: 'Schedules',       icon: 'calendar_today',path: '/results'   },
  { key: 'processing', label: 'Conflict Solver', icon: 'auto_fix_high', path: '/processing'},
  { key: 'calendar',   label: 'Detailed View',   icon: 'calendar_month',path: '/calendar'  },
  { key: 'history',    label: 'History',         icon: 'history',       path: '#'          },
  { key: 'settings',   label: 'Settings',        icon: 'settings',      path: '#'          },
]

/* ── Sidebar ───────────────────────────────────────────────────── */
export function Sidebar({ current }) {
  const navigate = useNavigate()
  return (
    <aside
      className="h-screen w-64 fixed left-0 top-0 hidden md:flex flex-col z-40 py-7 px-4 gap-4"
      style={{
        background: 'rgba(6,14,32,0.55)',
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <button
        className="flex items-center gap-3 px-2 mb-6 text-left"
        onClick={() => navigate('/')}
      >
        <BrandMark size={42} subtitle="Exam Coordinator" />
      </button>

      <nav className="flex-1 flex flex-col gap-1.5">
        {NAV.map((item) => {
          const active = current === item.key
          return (
            <button
              key={item.key}
              onClick={() => item.path !== '#' && navigate(item.path)}
              className={`group relative flex items-center gap-4 py-3 px-4 rounded-r-full font-semibold text-[13px] transition-all duration-200 text-left ${
                active
                  ? 'text-on-surface'
                  : 'text-on-surface-variant/80 hover:text-primary hover:translate-x-1'
              }`}
              style={
                active
                  ? {
                      background: 'rgba(173,198,255,0.10)',
                      boxShadow: 'inset 0 0 0 1px rgba(173,198,255,0.18), 0 0 24px rgba(173,198,255,0.12)',
                    }
                  : {}
              }
            >
              {active && (
                <span
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{
                    background: 'linear-gradient(180deg, #adc6ff, #8b5cf6)',
                    boxShadow: '0 0 12px rgba(173,198,255,0.6)',
                  }}
                />
              )}
              <Icon name={item.icon} fill={active} className={active ? 'text-primary' : ''} />
              <span className="tracking-wide">{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-white/5 pt-4 flex flex-col gap-1">
        <button className="flex items-center gap-4 py-2.5 px-4 text-on-surface-variant hover:text-primary text-[13px] font-semibold transition-all">
          <Icon name="help" />
          <span>Help Center</span>
        </button>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-4 py-2.5 px-4 text-on-surface-variant hover:text-error text-[13px] font-semibold transition-all"
        >
          <Icon name="logout" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  )
}

/* ── TopBar ────────────────────────────────────────────────────── */
export function TopBar({ title, subtitle, accent = false, right }) {
  return (
    <header
      className="fixed top-0 right-0 left-0 md:left-64 h-16 flex justify-between items-center px-6 md:px-12 z-30"
      style={{
        background: 'rgba(6,14,32,0.6)',
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}
    >
      <div className="flex items-center gap-4">
        <h2 className={`font-bold text-[22px] md:text-[26px] ${accent ? 'grad-text-cool' : 'text-on-surface'}`}>
          {title}
        </h2>
        {subtitle && (
          <span className="hidden md:inline text-[11px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">
            {subtitle}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {right}
        <button className="p-2 rounded-full hover:bg-white/5 transition-all active:scale-95 text-on-surface-variant">
          <Icon name="notifications" />
          <span className="sr-only">Notifications</span>
        </button>
        <div className="h-7 w-px bg-white/10 mx-2" />
        <button className="flex items-center gap-3 p-1 pl-3 pr-1 rounded-full hover:bg-white/5 transition-all active:scale-95">
          <span className="hidden lg:flex flex-col items-end leading-tight">
            <span className="text-[12px] font-semibold text-on-surface">Dr. Aris Thorne</span>
            <span className="text-[9px] uppercase tracking-widest text-on-surface-variant/60">Lead Coordinator</span>
          </span>
          <div
            className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-primary/30 flex items-center justify-center text-white text-[12px] font-bold"
            style={{ background: 'linear-gradient(135deg, #4d8eff, #571bc1)' }}
          >
            AT
          </div>
        </button>
      </div>
    </header>
  )
}

/* ── WorkspaceShell ────────────────────────────────────────────── */
export function WorkspaceShell({ current, title, subtitle, accent = true, right, children }) {
  return (
    <>
      <AmbientOrbs variant="workspace" />
      <Sidebar current={current} />
      <TopBar title={title} subtitle={subtitle} accent={accent} right={right} />
      <main className="relative z-10 md:pl-64 pt-16 min-h-screen">
        <div className="px-6 md:px-12 py-10 max-w-[1440px] mx-auto">
          {children}
        </div>
      </main>
    </>
  )
}

/* ── useCurrent (derive active sidebar key from route) ─────────── */
export function useCurrent() {
  const location = useLocation()
  const map = {
    '/dashboard':  'dashboard',
    '/results':    'results',
    '/processing': 'processing',
    '/calendar':   'calendar',
  }
  return map[location.pathname] || 'dashboard'
}
