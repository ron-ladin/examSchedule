/**
 * SCRUM-85 — ExamPeriodCalendar: mini calendar per period with exclusion toggles.
 * SCRUM-86 — DateRangePicker: start/end date inputs wired to PATCH /api/periods/{key}/range.
 *
 * Fetches GET /api/periods → renders one collapsible panel per (semester, moed) pair.
 * Each panel shows:
 *   • Date-range inputs (SCRUM-86) → PATCH /api/periods/{key}/range
 *   • Mini calendar grid → click to toggle excluded dates
 *                       → PATCH /api/periods/{key}/exclusions
 *
 * Props:
 *   toast  (msg, type) => void
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { api, ApiError } from '../api/client'
import { SEMESTER_LABELS, MOED_LABELS } from '../models/types'

const DAYS_SHORT  = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function pad(n) { return String(n).padStart(2, '0') }
function toISO(y, m, d) { return `${y}-${pad(m + 1)}-${pad(d)}` }

// ── Mini calendar grid ─────────────────────────────────────────────────────

function MiniCalendar({ startDate, endDate, excludedDates, onToggleExclusion }) {
  const start = startDate ? new Date(startDate + 'T00:00:00') : null
  const end   = endDate   ? new Date(endDate   + 'T00:00:00') : null

  const months = useMemo(() => {
    if (!start || !end) return []
    const result = []
    let cur = new Date(start.getFullYear(), start.getMonth(), 1)
    const endMonth = new Date(end.getFullYear(), end.getMonth(), 1)
    while (cur <= endMonth) {
      result.push({ year: cur.getFullYear(), month: cur.getMonth() })
      cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1)
    }
    return result
  }, [startDate, endDate])

  if (!start || !end) {
    return (
      <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--outline)', padding: '0.75rem 0' }}>
        Set a start and end date to see the calendar.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem' }}>
      {months.map(({ year, month }) => {
        const firstDay   = new Date(year, month, 1).getDay()
        const daysInMonth = new Date(year, month + 1, 0).getDate()
        const cells = []
        for (let i = 0; i < firstDay; i++) cells.push(null)
        for (let d = 1; d <= daysInMonth; d++) cells.push(d)

        return (
          <div key={`${year}-${month}`} style={{ minWidth: '196px' }}>
            {/* Month label */}
            <p
              style={{
                fontFamily: 'Sora, sans-serif',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--on-surface)',
                marginBottom: '0.4rem',
                letterSpacing: '-0.01em',
              }}
            >
              {MONTHS_SHORT[month]} {year}
            </p>

            {/* Day-of-week headers */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: '2px' }}>
              {DAYS_SHORT.map(d => (
                <div
                  key={d}
                  style={{
                    textAlign: 'center',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.55rem',
                    color: 'var(--outline)',
                    letterSpacing: '0.03em',
                    padding: '2px 0',
                  }}
                >
                  {d}
                </div>
              ))}
            </div>

            {/* Date cells */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px' }}>
              {cells.map((day, i) => {
                if (!day) return <div key={`e-${i}`} />
                const iso = toISO(year, month, day)
                const date = new Date(iso + 'T00:00:00')
                const isInRange   = date >= start && date <= end
                const isExcluded  = excludedDates.includes(iso)
                const isRangeEdge = iso === startDate || iso === endDate

                return (
                  <button
                    key={iso}
                    onClick={() => isInRange && onToggleExclusion(iso)}
                    disabled={!isInRange}
                    title={isExcluded ? 'Excluded — click to include' : isInRange ? 'Click to exclude' : ''}
                    style={{
                      width: '100%',
                      aspectRatio: '1',
                      borderRadius: '4px',
                      border: isRangeEdge
                        ? '1.5px solid #3b82f6'
                        : 'none',
                      background: isExcluded
                        ? 'rgba(186,26,26,0.15)'
                        : isRangeEdge
                        ? 'rgba(59,130,246,0.2)'
                        : isInRange
                        ? 'rgba(59,130,246,0.06)'
                        : 'transparent',
                      fontFamily: 'Inter, sans-serif',
                      fontSize: '0.65rem',
                      color: isExcluded
                        ? '#ba1a1a'
                        : isInRange
                        ? 'var(--on-surface)'
                        : 'var(--outline-variant)',
                      cursor: isInRange ? 'pointer' : 'default',
                      transition: 'background 0.12s',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: 0,
                    }}
                  >
                    {day}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Single period panel ────────────────────────────────────────────────────

function PeriodPanel({ period, onUpdate, toast }) {
  const [isOpen,        setIsOpen]        = useState(false)
  const [startDate,     setStartDate]     = useState(period.startDate   ?? '')
  const [endDate,       setEndDate]       = useState(period.endDate     ?? '')
  const [excludedDates, setExcludedDates] = useState(period.excludedDates ?? [])
  const [savingRange,   setSavingRange]   = useState(false)
  const [dirty,         setDirty]         = useState(false)

  // ── SCRUM-86: save date range ──────────────────────────────────────────
  const handleSaveRange = useCallback(async () => {
    if (!startDate || !endDate) {
      toast?.('Please set both a start and end date.', 'warning')
      return
    }
    setSavingRange(true)
    try {
      await api.updatePeriodRange(period.key, startDate, endDate)
      setDirty(false)
      toast?.(`Range saved for ${period.key}.`, 'success')
      onUpdate?.(period.key, { startDate, endDate })
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Save failed (${err.status})`
        : 'Backend offline — range not persisted.'
      toast?.(msg, 'warning')
    } finally {
      setSavingRange(false)
    }
  }, [period.key, startDate, endDate, toast, onUpdate])

  // ── SCRUM-85: toggle exclusion ─────────────────────────────────────────
  const handleToggleExclusion = useCallback(async (iso) => {
    const next = excludedDates.includes(iso)
      ? excludedDates.filter(d => d !== iso)
      : [...excludedDates, iso].sort()
    setExcludedDates(next)

    try {
      await api.updatePeriodExclusions(period.key, next)
      onUpdate?.(period.key, { excludedDates: next })
    } catch (err) {
      setExcludedDates(excludedDates)  // rollback
      const msg = err instanceof ApiError
        ? `Exclusion save failed (${err.status})`
        : 'Backend offline — exclusion not persisted.'
      toast?.(msg, 'warning')
    }
  }, [excludedDates, period.key, toast, onUpdate])

  const semLabel  = SEMESTER_LABELS[period.semester] ?? period.semester
  const moedLabel = MOED_LABELS[period.moed]         ?? period.moed

  const inputStyle = {
    padding: '0.45rem 0.75rem',
    borderRadius: '0.5rem',
    border: '1.5px solid var(--outline-variant)',
    background: 'var(--surface-container-low)',
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: '0.8rem',
    color: 'var(--on-surface)',
    outline: 'none',
  }

  return (
    <div
      style={{
        borderRadius: '0.875rem',
        border: `1.5px solid ${isOpen ? 'var(--primary)' : 'var(--outline-variant)'}`,
        background: 'var(--surface-container-lowest)',
        overflow: 'hidden',
        transition: 'border-color 0.15s',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setIsOpen(o => !o)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '0.875rem',
          padding: '0.875rem 1rem',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span
          className="material-icons-round"
          style={{ fontSize: '1.1rem', color: 'var(--primary)', flexShrink: 0 }}
        >
          date_range
        </span>
        <div style={{ flex: 1 }}>
          <p
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.88rem',
              fontWeight: 700,
              color: 'var(--on-surface)',
              letterSpacing: '-0.01em',
            }}
          >
            {semLabel}
            <span style={{ color: 'var(--outline)', fontWeight: 400 }}> — </span>
            {moedLabel}
          </p>
          {startDate && endDate ? (
            <p
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.67rem',
                color: 'var(--outline)',
                marginTop: '0.1rem',
              }}
            >
              {startDate} → {endDate}
              {excludedDates.length > 0 && ` · ${excludedDates.length} excluded`}
            </p>
          ) : (
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.72rem', color: 'var(--warning)', marginTop: '0.1rem' }}>
              No date range set
            </p>
          )}
        </div>
        <span
          className="material-icons-round"
          style={{
            fontSize: '1.1rem',
            color: 'var(--on-surface-variant)',
            transform: isOpen ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s',
            flexShrink: 0,
          }}
        >
          expand_more
        </span>
      </button>

      {/* Body */}
      {isOpen && (
        <div style={{ padding: '0 1rem 1.25rem', borderTop: '1px solid var(--outline-variant)' }}>

          {/* SCRUM-86: Date range pickers */}
          <div style={{ marginTop: '1rem', marginBottom: '1.25rem' }}>
            <p
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.65rem',
                color: 'var(--outline)',
                letterSpacing: '0.06em',
                marginBottom: '0.6rem',
              }}
            >
              EXAM WINDOW
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div>
                <label
                  style={{
                    display: 'block',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '0.72rem',
                    color: 'var(--on-surface-variant)',
                    marginBottom: '0.25rem',
                  }}
                >
                  Start date
                </label>
                <input
                  type="date"
                  value={startDate}
                  style={inputStyle}
                  onChange={e => { setStartDate(e.target.value); setDirty(true) }}
                />
              </div>
              <div>
                <label
                  style={{
                    display: 'block',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '0.72rem',
                    color: 'var(--on-surface-variant)',
                    marginBottom: '0.25rem',
                  }}
                >
                  End date
                </label>
                <input
                  type="date"
                  value={endDate}
                  min={startDate}
                  style={inputStyle}
                  onChange={e => { setEndDate(e.target.value); setDirty(true) }}
                />
              </div>
              {dirty && (
                <button
                  className="btn-outline"
                  onClick={handleSaveRange}
                  disabled={savingRange}
                  style={{ fontSize: '0.78rem', padding: '0.45rem 1rem', opacity: savingRange ? 0.6 : 1 }}
                >
                  {savingRange
                    ? <span className="material-icons-round" style={{ fontSize: '0.9rem', animation: 'spin 1s linear infinite' }}>sync</span>
                    : <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>save</span>
                  }
                  Save Range
                </button>
              )}
            </div>
          </div>

          {/* SCRUM-85: Mini calendar with exclusion toggle */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
              <p
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.65rem',
                  color: 'var(--outline)',
                  letterSpacing: '0.06em',
                }}
              >
                EXCLUSIONS
              </p>
              {excludedDates.length > 0 && (
                <span
                  className="chip chip-red"
                  style={{ fontSize: '0.6rem' }}
                >
                  {excludedDates.length} blocked
                </span>
              )}
            </div>
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.73rem',
                color: 'var(--on-surface-variant)',
                marginBottom: '0.875rem',
                lineHeight: 1.5,
              }}
            >
              Click a date to toggle it as excluded. Red = blocked from scheduling.
            </p>

            <MiniCalendar
              startDate={startDate}
              endDate={endDate}
              excludedDates={excludedDates}
              onToggleExclusion={handleToggleExclusion}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function ExamPeriodCalendar({ toast }) {
  const [periods,  setPeriods]  = useState([])
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    let cancelled = false
    api.getPeriods()
      .then(data => { if (!cancelled) setPeriods(data ?? []) })
      .catch(err => {
        if (cancelled) return
        const msg = err instanceof ApiError
          ? `Could not load periods (${err.status})`
          : 'Backend offline — using mock period data.'
        toast?.(msg, 'warning')
        if (!cancelled) setPeriods(MOCK_PERIODS)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleUpdate = useCallback((key, patch) => {
    setPeriods(prev => prev.map(p => p.key === key ? { ...p, ...patch } : p))
  }, [])

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <div style={{ marginBottom: '1rem' }}>
        <h3
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: '0.95rem',
            fontWeight: 700,
            color: 'var(--on-surface)',
            letterSpacing: '-0.01em',
          }}
        >
          Exam Periods
        </h3>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', marginTop: '0.15rem' }}>
          Configure date windows and exclusions for each semester / moed.
        </p>
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1.5rem', color: 'var(--outline)' }}>
          <span className="material-icons-round" style={{ fontSize: '1.25rem', animation: 'spin 1s linear infinite' }}>sync</span>
          <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem' }}>Loading exam periods...</span>
        </div>
      ) : periods.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--outline)' }}>
          <span className="material-icons-round" style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}>event_busy</span>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem' }}>
            No periods found. Upload <span className="mono" style={{ color: 'var(--primary)' }}>dates.txt</span> first.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {periods.map(period => (
            <PeriodPanel
              key={period.key}
              period={period}
              onUpdate={handleUpdate}
              toast={toast}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Mock fallback when backend is offline ──────────────────────────────────
const MOCK_PERIODS = [
  {
    key:           'FALL-Aleph',
    semester:      'FALL',
    moed:          'Aleph',
    startDate:     '2025-01-12',
    endDate:       '2025-02-06',
    excludedDates: ['2025-01-20', '2025-01-27'],
  },
  {
    key:           'FALL-Bet',
    semester:      'FALL',
    moed:          'Bet',
    startDate:     '2025-02-16',
    endDate:       '2025-03-06',
    excludedDates: [],
  },
  {
    key:           'SPRI-Aleph',
    semester:      'SPRI',
    moed:          'Aleph',
    startDate:     '2025-06-15',
    endDate:       '2025-07-10',
    excludedDates: ['2025-06-22'],
  },
  {
    key:           'SPRI-Bet',
    semester:      'SPRI',
    moed:          'Bet',
    startDate:     '2025-07-20',
    endDate:       '2025-08-07',
    excludedDates: [],
  },
]
