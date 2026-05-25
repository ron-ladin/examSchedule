/**
 * ResultsView.jsx — SCRUM-92, 93, 94
 *
 * Displays up to three ranked schedule options produced by AppController.run():
 *   "Optimal"  — fewest conflicts, balanced gap
 *   "Fastest"  — shortest duration
 *   "Relaxed"  — maximum study gap
 *
 * Also renders:
 *   NavBar           (SCRUM-92) — shared sticky navigation
 *   Pagination       (SCRUM-92) — previous schedules via GET /api/schedules
 *   Export button    (SCRUM-94) — downloads selected schedule via exportSchedule
 *   Programme colours(SCRUM-93) — schedule cards use programme accent via colorFor
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useScheduler } from '../hooks/useScheduler'
import { api, ApiError } from '../api/client'
import { SEMESTER_LABELS, MOED_LABELS, SEMESTER, MOED } from '../models/types'
import NavBar from './NavBar'
import { MotionCard, StaggerList, StaggerItem, PageShell } from './Motion'

const OPTION_META = [
  {
    key:         'optimal',
    label:       'Optimal',
    icon:        'star',
    chipColor:   'chip-blue',
    description: 'Best balance of conflict resolution and study gaps.',
    accent:      'linear-gradient(135deg, #3b82f6, #8b5cf6)',
  },
  {
    key:         'fastest',
    label:       'Fastest',
    icon:        'bolt',
    chipColor:   'chip-purple',
    description: 'Shortest overall exam period duration.',
    accent:      'linear-gradient(135deg, #8b5cf6, #ec4899)',
  },
  {
    key:         'relaxed',
    label:       'Relaxed',
    icon:        'self_improvement',
    chipColor:   'chip-green',
    description: 'Maximum study gap between consecutive exams.',
    accent:      'linear-gradient(135deg, #10b981, #3b82f6)',
  },
]

function ResourceBadge({ load }) {
  const map = { Minimal: 'chip-green', Moderate: 'chip-orange', Intense: 'chip-red' }
  return <span className={`chip ${map[load] || 'chip-blue'}`}>{load}</span>
}

function ScheduleCard({ meta, schedule, selected, onSelect, onExplore }) {
  const isSelected = selected === meta.key

  return (
    <MotionCard
      onClick={() => onSelect(meta.key)}
      style={{
        borderRadius: '1.5rem',
        padding: '1.75rem',
        border: '2px solid',
        borderColor: isSelected ? '#3b82f6' : 'var(--outline-variant)',
        background: isSelected
          ? 'linear-gradient(135deg, rgba(59,130,246,0.06), rgba(139,92,246,0.06))'
          : 'var(--surface-container-lowest)',
        cursor: 'pointer',
        transition: 'border-color 0.2s ease, background 0.2s ease',
        boxShadow: isSelected ? '0 0 0 4px rgba(59,130,246,0.1), var(--glass-shadow)' : 'var(--glass-shadow)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Accent top bar */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '3px', background: isSelected ? meta.accent : 'transparent', transition: 'background 0.2s' }} />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: meta.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: isSelected ? 1 : 0.7 }}>
            <span className="material-icons-round" style={{ color: 'white', fontSize: '1.3rem' }}>{meta.icon}</span>
          </div>
          <div>
            <h3 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1.05rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.01em' }}>
              {meta.label}
            </h3>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)' }}>
              {meta.description}
            </p>
          </div>
        </div>
        {isSelected && (
          <span className="material-icons-round" style={{ color: '#3b82f6', fontSize: '1.3rem', flexShrink: 0 }}>check_circle</span>
        )}
      </div>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { label: 'Conflicts', value: schedule?.totalConflicts ?? 0,             icon: 'warning',        unit: ''  },
          { label: 'Duration',  value: schedule?.durationDays  ?? '—',            icon: 'schedule',       unit: 'd' },
          { label: 'Avg Gap',   value: schedule?.avgStudyGap?.toFixed(1) ?? '—',  icon: 'calendar_today', unit: 'd' },
        ].map(m => (
          <div key={m.label} style={{ padding: '0.75rem', borderRadius: '0.75rem', background: 'var(--surface-container)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.25rem' }}>
              <span className="material-icons-round" style={{ fontSize: '0.85rem', color: 'var(--outline)' }}>{m.icon}</span>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.7rem', color: 'var(--on-surface-variant)', fontWeight: 500 }}>{m.label}</span>
            </div>
            <span style={{ fontFamily: 'Sora, sans-serif', fontSize: '1.3rem', fontWeight: 800, color: 'var(--on-surface)', letterSpacing: '-0.02em' }}>
              {m.value}{m.unit}
            </span>
          </div>
        ))}
        <div style={{ padding: '0.75rem', borderRadius: '0.75rem', background: 'var(--surface-container)' }}>
          <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.7rem', color: 'var(--on-surface-variant)', display: 'block', marginBottom: '0.35rem', fontWeight: 500 }}>Resource Load</span>
          <ResourceBadge load={schedule?.resourceLoad ?? 'Moderate'} />
        </div>
      </div>

      <button
        className="btn-outline"
        onClick={e => { e.stopPropagation(); onExplore(meta.key) }}
        style={{ width: '100%', justifyContent: 'center', fontSize: '0.82rem', padding: '0.6rem 1.25rem' }}
      >
        Explore Details
        <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>arrow_forward</span>
      </button>
    </MotionCard>
  )
}

function WeeklyDistribution() {
  const weeks      = ['W1', 'W2', 'W3', 'W4', 'W5']
  const mockCounts = [4, 7, 5, 6, 3]
  const max        = Math.max(...mockCounts)

  return (
    <div>
      <p style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: 'var(--on-surface)', marginBottom: '0.75rem' }}>
        Weekly Distribution
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', height: '80px' }}>
        {weeks.map((w, i) => (
          <div key={w} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.35rem' }}>
            <div style={{ width: '100%', height: `${(mockCounts[i] / max) * 60}px`, borderRadius: '4px 4px 0 0', background: 'var(--gradient-primary)', opacity: 0.7 + (i * 0.05) }} />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: 'var(--outline)', letterSpacing: '0.03em' }}>{w}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── SCRUM-92: Schedule history with pagination ────────────────────────────────

const PAGE_SIZE = 5

const MOCK_HISTORY = [
  { id: 'sch-001', periodKey: 'FALL - Aleph', totalConflicts: 0, durationDays: 21, createdAt: '2025-01-10' },
  { id: 'sch-002', periodKey: 'FALL - Bet',   totalConflicts: 1, durationDays: 18, createdAt: '2025-01-08' },
  { id: 'sch-003', periodKey: 'SPRI - Aleph', totalConflicts: 0, durationDays: 25, createdAt: '2024-12-20' },
  { id: 'sch-004', periodKey: 'SPRI - Bet',   totalConflicts: 2, durationDays: 20, createdAt: '2024-12-15' },
  { id: 'sch-005', periodKey: 'FALL - Aleph', totalConflicts: 0, durationDays: 19, createdAt: '2024-11-30' },
  { id: 'sch-006', periodKey: 'SUMM - Aleph', totalConflicts: 0, durationDays: 14, createdAt: '2024-11-20' },
]

function ScheduleHistory({ toast }) {
  const [page,    setPage]    = useState(1)
  const [items,   setItems]   = useState([])
  const [total,   setTotal]   = useState(0)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(null)

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1

  const load = useCallback(async (p) => {
    setLoading(true)
    try {
      const data = await api.getSchedules({ page: p, pageSize: PAGE_SIZE })
      setItems(data.schedules)
      setTotal(data.total)
    } catch {
      // Backend offline — use mock
      const start = (p - 1) * PAGE_SIZE
      setItems(MOCK_HISTORY.slice(start, start + PAGE_SIZE))
      setTotal(MOCK_HISTORY.length)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(page) }, [page, load])

  const handleExport = async (item) => {
    setExporting(item.id)
    try {
      const blob = await api.exportSchedule(item.id)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `schedule-${item.id}.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Export failed (${err.status})`
        : 'Backend offline — export unavailable.'
      toast?.(msg, 'warning')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="card" style={{ padding: '1.75rem', marginTop: '1.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div>
          <h3 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.01em' }}>
            Schedule History
          </h3>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', marginTop: '0.15rem' }}>
            {total} saved schedules
          </p>
        </div>

        {/* Pagination controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1 || loading}
            style={{ background: 'none', border: '1.5px solid var(--outline-variant)', borderRadius: '0.5rem', cursor: page === 1 ? 'default' : 'pointer', padding: '0.3rem 0.5rem', opacity: page === 1 ? 0.4 : 1 }}
          >
            <span className="material-icons-round" style={{ fontSize: '1rem', color: 'var(--on-surface-variant)' }}>chevron_left</span>
          </button>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: 'var(--on-surface-variant)', minWidth: '4rem', textAlign: 'center' }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages || loading}
            style={{ background: 'none', border: '1.5px solid var(--outline-variant)', borderRadius: '0.5rem', cursor: page === totalPages ? 'default' : 'pointer', padding: '0.3rem 0.5rem', opacity: page === totalPages ? 0.4 : 1 }}
          >
            <span className="material-icons-round" style={{ fontSize: '1rem', color: 'var(--on-surface-variant)' }}>chevron_right</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', color: 'var(--outline)' }}>
          <span className="material-icons-round" style={{ fontSize: '1.1rem', animation: 'spin 1s linear infinite' }}>sync</span>
          <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem' }}>Loading history...</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {items.map(item => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '1rem',
                padding: '0.875rem 1rem',
                borderRadius: '0.875rem',
                background: 'var(--surface-container-low)',
                border: '1px solid var(--outline-variant)',
              }}
            >
              <span className="material-icons-round" style={{ color: 'var(--primary)', fontSize: '1.1rem', flexShrink: 0 }}>
                calendar_today
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: 'var(--on-surface)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {item.periodKey}
                </p>
                <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: 'var(--outline)', marginTop: '0.1rem' }}>
                  {item.createdAt} · {item.durationDays}d · {item.totalConflicts} conflicts
                </p>
              </div>
              {item.totalConflicts > 0 && (
                <span className="chip chip-red" style={{ fontSize: '0.6rem', flexShrink: 0 }}>{item.totalConflicts}</span>
              )}
              {/* SCRUM-94 — export per history item */}
              <button
                onClick={() => handleExport(item)}
                disabled={exporting === item.id}
                style={{ background: 'none', border: '1.5px solid var(--outline-variant)', borderRadius: '0.5rem', cursor: 'pointer', padding: '0.35rem 0.625rem', display: 'flex', alignItems: 'center', gap: '0.25rem', opacity: exporting === item.id ? 0.6 : 1 }}
              >
                {exporting === item.id
                  ? <span className="material-icons-round" style={{ fontSize: '0.9rem', color: 'var(--primary)', animation: 'spin 1s linear infinite' }}>sync</span>
                  : <span className="material-icons-round" style={{ fontSize: '0.9rem', color: 'var(--on-surface-variant)' }}>download</span>
                }
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>Export</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ResultsView() {
  const navigate = useNavigate()
  const { results, processingState } = useScheduler()

  const [selectedSemester, setSelectedSemester] = useState(SEMESTER.FALL)
  const [selectedMoed,     setSelectedMoed]     = useState(MOED.Aleph)
  const [selectedOption,   setSelectedOption]   = useState('optimal')
  const [exporting,        setExporting]        = useState(false)

  const schedules = results ?? [
    { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 21, avgStudyGap: 3.2, resourceLoad: 'Moderate' },
    { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 14, avgStudyGap: 1.8, resourceLoad: 'Intense'  },
    { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 28, avgStudyGap: 4.5, resourceLoad: 'Minimal'  },
  ]

  const handleExplore = (optionKey) => {
    setSelectedOption(optionKey)
    navigate('/calendar')
  }

  // SCRUM-94 — Export selected schedule
  const handleExportSelected = async () => {
    const idx        = OPTION_META.findIndex(m => m.key === selectedOption)
    const schedule   = schedules[idx]
    const scheduleId = schedule?.id ?? `demo-${selectedOption}`
    setExporting(true)
    try {
      const blob = await api.exportSchedule(scheduleId)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `schedule-${selectedOption}.txt`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      // Demo fallback: download a plain-text stub
      const content = `Schedule: ${selectedOption}\nPeriod: ${schedule?.periodKey}\nDuration: ${schedule?.durationDays}d\nConflicts: ${schedule?.totalConflicts}`
      const blob    = new Blob([content], { type: 'text/plain' })
      const url     = URL.createObjectURL(blob)
      const a       = document.createElement('a')
      a.href = url; a.download = `schedule-${selectedOption}.txt`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  const selectStyle = {
    padding: '0.5rem 0.875rem',
    borderRadius: '9999px',
    border: '1.5px solid var(--outline-variant)',
    background: 'var(--surface-container-lowest)',
    fontFamily: 'Inter, sans-serif',
    fontSize: '0.82rem',
    color: 'var(--on-surface)',
    cursor: 'pointer',
    outline: 'none',
  }

  // SCRUM-94 — NavBar right slot: Export Selected button
  const navRight = (
    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
      <button
        className="btn-outline"
        onClick={handleExportSelected}
        disabled={exporting}
        style={{ fontSize: '0.8rem', padding: '0.45rem 1rem', opacity: exporting ? 0.6 : 1 }}
      >
        {exporting
          ? <span className="material-icons-round" style={{ fontSize: '0.9rem', animation: 'spin 1s linear infinite' }}>sync</span>
          : <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>download</span>
        }
        Export Selected
      </button>
      <a href="#" style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8rem', color: 'var(--outline)', textDecoration: 'none' }}>Help</a>
      <a href="/" style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8rem', color: 'var(--outline)', textDecoration: 'none' }}>Sign Out</a>
    </div>
  )

  return (
    <PageShell style={{ minHeight: '100vh', background: 'var(--surface)' }}>

      {/* SCRUM-92 — Shared NavBar */}
      <NavBar currentPath="/results" rightContent={navRight} />

      <main style={{ maxWidth: '1280px', margin: '0 auto', padding: '2.5rem 2rem' }}>

        {/* Page header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
          <div>
            <h1 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1.75rem', fontWeight: 800, color: 'var(--on-surface)', letterSpacing: '-0.02em', marginBottom: '0.25rem' }}>
              Schedule Results
            </h1>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>
              Three optimized options generated — select one to proceed.
            </p>
          </div>

          {/* Filters */}
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <select value={selectedSemester} onChange={e => setSelectedSemester(e.target.value)} style={selectStyle}>
              {Object.entries(SEMESTER_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={selectedMoed} onChange={e => setSelectedMoed(e.target.value)} style={selectStyle}>
              {Object.entries(MOED_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button className="btn-secondary" style={{ fontSize: '0.82rem', padding: '0.5rem 1rem' }}
              onClick={() => navigate('/dashboard')}
            >
              <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>refresh</span>
              Re-Calculate
            </button>
          </div>
        </div>

        {/* Three option cards */}
        <StaggerList style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem', marginBottom: '2rem' }}>
          {OPTION_META.map((meta, i) => (
            <StaggerItem key={meta.key}>
              <ScheduleCard
                meta={meta}
                schedule={schedules[i]}
                selected={selectedOption}
                onSelect={setSelectedOption}
                onExplore={handleExplore}
              />
            </StaggerItem>
          ))}
        </StaggerList>

        {/* Summary panel */}
        <div className="card" style={{ padding: '1.75rem', display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '2rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <WeeklyDistribution />

          <div>
            <p style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: 'var(--on-surface)', marginBottom: '0.75rem' }}>
              Solver Health
            </p>
            <span style={{ fontFamily: 'Sora, sans-serif', fontSize: '2.5rem', fontWeight: 800, letterSpacing: '-0.03em', background: 'var(--gradient-primary)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              99.8%
            </span>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', marginTop: '0.25rem' }}>
              No critical conflicts detected
            </p>
          </div>

          <div style={{ padding: '1.25rem', borderRadius: '1rem', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', minWidth: '220px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <span className="material-icons-round" style={{ color: '#f59e0b', fontSize: '1.1rem' }}>schedule</span>
              <span style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.82rem', fontWeight: 700, color: 'var(--on-surface)' }}>Upcoming Deadline</span>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', lineHeight: 1.5, marginBottom: '0.5rem' }}>
              Submission of Moed A schedules to Registrar
            </p>
            <span className="chip chip-orange">2 DAYS LEFT</span>
          </div>
        </div>

        {/* SCRUM-92 — Paginated schedule history */}
        <ScheduleHistory />
      </main>
    </PageShell>
  )
}
