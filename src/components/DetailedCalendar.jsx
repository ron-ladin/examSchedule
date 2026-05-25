/**
 * DetailedCalendar.jsx — SCRUM-90, 91, 92, 93, 94
 *
 * Three view modes:
 *   Month  — monthly calendar grid (default)
 *   List   — SCRUM-91: SemesterGroupLayout — exams grouped by semester
 *   Today  — jumps to today's date in month view
 *
 * Uses:
 *   NavBar            (SCRUM-92) — shared sticky top navigation
 *   ExamSlot          (SCRUM-90) — coloured compact + full exam cards
 *   SemesterGroupLayout (SCRUM-91)
 *   colorFor          (SCRUM-93) — programme colour applied to calendar cells
 *   Export button     (SCRUM-94) — calls api.exportSchedule → triggers download
 */

import { useState, useMemo } from 'react'
import { useScheduler } from '../hooks/useScheduler'
import { api, ApiError } from '../api/client'
import { colorFor } from '../utils/progColor'
import NavBar from './NavBar'
import ExamSlot from './ExamSlot'
import SemesterGroupLayout from './SemesterGroupLayout'
import { MotionCard, PageShell } from './Motion'

const DAYS_OF_WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

// Mock exam data — replace with useScheduler().results[selectedOption].assignments
const MOCK_EXAMS = [
  { courseId: '83512', courseName: 'Advanced Algorithms', instructor: 'Prof. R. Chen', date: '2024-12-05', conflicts: 1, room: 'Science Building, Hall A-105', time: '14:00 - 17:00', proctors: ['Dr. A. Cohen', 'T. Shapiro'] },
  { courseId: '83401', courseName: 'Operating Systems',   instructor: 'Dr. M. Levy',   date: '2024-12-09', conflicts: 0, room: 'Bldg B, Hall 201',             time: '09:00 - 12:00', proctors: ['Prof. Y. Klein'] },
  { courseId: '83301', courseName: 'Data Structures',     instructor: 'Dr. E. Golan',  date: '2024-12-12', conflicts: 0, room: 'Main Auditorium',               time: '10:00 - 13:00', proctors: ['Dr. S. Bar'] },
  { courseId: '83201', courseName: 'Calculus 2',          instructor: 'Prof. O. Some', date: '2024-12-16', conflicts: 0, room: 'Hall C-301',                    time: '08:00 - 11:00', proctors: ['T. Rosen'] },
  { courseId: '83101', courseName: 'Physics 1',           instructor: 'Prof. B. Tal',  date: '2024-12-19', conflicts: 0, room: 'Physics Lab, Wing D',            time: '13:00 - 16:00', proctors: ['Dr. N. Cohen'] },
]

function pad(n) { return String(n).padStart(2, '0') }
function isoDate(year, month, day) { return `${year}-${pad(month + 1)}-${pad(day)}` }

// ── Calendar grid with programme colour coding (SCRUM-93) ─────────────────────

function CalendarGrid({ year, month, exams, selectedDate, onSelect }) {
  const firstDay    = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const examsByDate = useMemo(() => {
    const map = {}
    exams.forEach(e => {
      if (!map[e.date]) map[e.date] = []
      map[e.date].push(e)
    })
    return map
  }, [exams])

  const cells = []
  for (let i = 0; i < firstDay; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)

  return (
    <div>
      {/* Day headers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', marginBottom: '0.25rem' }}>
        {DAYS_OF_WEEK.map(d => (
          <div
            key={d}
            style={{
              textAlign: 'center',
              padding: '0.5rem 0',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.7rem',
              color: 'var(--outline)',
              letterSpacing: '0.04em',
            }}
          >
            {d}
          </div>
        ))}
      </div>

      {/* Cells */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px' }}>
        {cells.map((day, i) => {
          if (!day) return <div key={`e-${i}`} />
          const iso       = isoDate(year, month, day)
          const dayExams  = examsByDate[iso] || []
          const hasConflict = dayExams.some(e => e.conflicts > 0)
          const isSelected  = iso === selectedDate
          const isToday     = iso === new Date().toISOString().slice(0, 10)

          return (
            <MotionCard
              key={iso}
              onClick={() => onSelect(iso)}
              style={{
                minHeight: '72px',
                borderRadius: '0.625rem',
                padding: '0.5rem',
                cursor: 'pointer',
                border: '1.5px solid',
                borderColor: isSelected
                  ? '#3b82f6'
                  : hasConflict
                  ? 'rgba(186,26,26,0.3)'
                  : dayExams.length > 0
                  ? 'rgba(59,130,246,0.25)'
                  : 'var(--outline-variant)',
                background: isSelected
                  ? 'linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))'
                  : hasConflict
                  ? 'rgba(186,26,26,0.06)'
                  : dayExams.length > 0
                  ? 'rgba(59,130,246,0.04)'
                  : 'var(--surface-container-lowest)',
                transition: 'border-color 0.15s, background 0.15s',
                boxShadow: isSelected ? '0 0 0 3px rgba(59,130,246,0.15)' : 'none',
              }}
            >
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '22px',
                  height: '22px',
                  borderRadius: '50%',
                  background: isToday ? 'var(--gradient-primary)' : 'transparent',
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.78rem',
                  fontWeight: isToday ? 700 : 400,
                  color: isToday ? 'white' : 'var(--on-surface)',
                  marginBottom: '0.25rem',
                }}
              >
                {day}
              </span>

              {/* Compact exam pills — SCRUM-90 colour coded (SCRUM-93) */}
              {dayExams.slice(0, 2).map(ex => (
                <ExamSlot key={ex.courseId} exam={ex} size="compact" />
              ))}
              {dayExams.length > 2 && (
                <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.6rem', color: 'var(--outline)' }}>
                  +{dayExams.length - 2}
                </span>
              )}
            </MotionCard>
          )
        })}
      </div>
    </div>
  )
}

// ── Detail sidebar using ExamSlot (SCRUM-90) ──────────────────────────────────

function ExamDetailSidebar({ date, exams }) {
  if (!date) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          gap: '0.75rem',
          padding: '2rem',
          textAlign: 'center',
        }}
      >
        <span className="material-icons-round" style={{ color: 'var(--outline-variant)', fontSize: '2.5rem' }}>
          event_note
        </span>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', color: 'var(--outline)' }}>
          Select a date to view exam details
        </p>
      </div>
    )
  }

  const d         = new Date(date + 'T00:00:00')
  const formatted = d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

  return (
    <div style={{ padding: '1.5rem', overflowY: 'auto' }}>
      <div style={{ marginBottom: '1.25rem' }}>
        <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'var(--outline)', letterSpacing: '0.06em', marginBottom: '0.25rem' }}>
          SELECTED DATE
        </p>
        <h3 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.01em' }}>
          {formatted}
        </h3>
      </div>

      {exams.length === 0 ? (
        <div style={{ padding: '1.25rem', borderRadius: '0.875rem', background: 'var(--surface-container)', textAlign: 'center' }}>
          <span className="material-icons-round" style={{ color: 'var(--success)', fontSize: '1.5rem', display: 'block', marginBottom: '0.4rem' }}>event_available</span>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: 'var(--on-surface-variant)' }}>No exams scheduled</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {exams.map(ex => <ExamSlot key={ex.courseId} exam={ex} size="full" />)}
        </div>
      )}
    </div>
  )
}

// ── Export helper (SCRUM-94) ──────────────────────────────────────────────────

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a   = document.createElement('a')
  a.href     = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DetailedCalendar() {
  const { results } = useScheduler()

  const [year,         setYear]        = useState(2024)
  const [month,        setMonth]       = useState(11)   // December = 11
  const [selectedDate, setSelectedDate] = useState(null)
  const [viewMode,     setViewMode]    = useState('month')   // 'today' | 'month' | 'list'
  const [exporting,    setExporting]   = useState(false)

  const exams = results?.[0]?.assignments?.length
    ? results[0].assignments
    : MOCK_EXAMS

  const selectedExams = useMemo(
    () => exams.filter(e => e.date === selectedDate),
    [exams, selectedDate],
  )

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }

  // SCRUM-94 — Export schedule
  const handleExport = async () => {
    setExporting(true)
    try {
      const scheduleId = results?.[0]?.id ?? 'demo-schedule'
      const blob       = await api.exportSchedule(scheduleId)
      downloadBlob(blob, `schedule-${scheduleId}.txt`)
    } catch {
      // In demo mode the backend isn't running — offer a CSV of mock data instead
      const csv = [
        'courseId,courseName,instructor,date,time,room',
        ...exams.map(e =>
          [e.courseId, `"${e.courseName}"`, e.instructor, e.date, e.time ?? '', e.room ?? ''].join(',')
        ),
      ].join('\n')
      downloadBlob(new Blob([csv], { type: 'text/csv' }), 'schedule-export.csv')
    } finally {
      setExporting(false)
    }
  }

  // ── NavBar right slot: Add Exam + Export ────────────────────────────────────
  const navRight = (
    <div style={{ display: 'flex', gap: '0.625rem', alignItems: 'center' }}>
      <button
        className="btn-outline"
        onClick={handleExport}
        disabled={exporting}
        style={{ fontSize: '0.8rem', padding: '0.45rem 1rem', opacity: exporting ? 0.6 : 1 }}
      >
        {exporting
          ? <span className="material-icons-round" style={{ fontSize: '0.9rem', animation: 'spin 1s linear infinite' }}>sync</span>
          : <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>download</span>
        }
        Export
      </button>
      <button className="btn-primary" style={{ padding: '0.5rem 1.25rem', fontSize: '0.82rem' }}>
        <span className="material-icons-round" style={{ fontSize: '0.9rem' }}>add</span>
        Add New Exam
      </button>
    </div>
  )

  return (
    <PageShell style={{ minHeight: '100vh', background: 'var(--surface)' }}>

      {/* SCRUM-92 — Shared NavBar */}
      <NavBar currentPath="/calendar" rightContent={navRight} />

      <div
        style={{
          maxWidth: '1280px',
          margin: '0 auto',
          padding: '2rem',
          display: viewMode === 'list' ? 'block' : 'grid',
          gridTemplateColumns: '1fr 320px',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        {/* ── List view (SCRUM-91) ────────────────────────────────────────── */}
        {viewMode === 'list' ? (
          <div className="card" style={{ padding: '1.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.75rem', flexWrap: 'wrap', gap: '0.75rem' }}>
              <h2 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1.15rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.02em' }}>
                All Exams by Semester
              </h2>
              <ViewToggle viewMode={viewMode} onChange={(m) => {
                setViewMode(m)
                if (m === 'today') {
                  const now = new Date()
                  setYear(now.getFullYear()); setMonth(now.getMonth())
                  setSelectedDate(now.toISOString().slice(0, 10))
                  setViewMode('month')
                }
              }} />
            </div>
            <SemesterGroupLayout exams={exams} onSelectExam={ex => {
              const d = new Date(ex.date + 'T00:00:00')
              setYear(d.getFullYear()); setMonth(d.getMonth())
              setSelectedDate(ex.date)
              setViewMode('month')
            }} />
          </div>
        ) : (
          <>
            {/* ── Calendar panel (Month / Today) ─────────────────────────── */}
            <div className="card" style={{ padding: '1.75rem' }}>

              {/* Calendar header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <button
                    onClick={prevMonth}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', borderRadius: '0.5rem' }}
                  >
                    <span className="material-icons-round" style={{ color: 'var(--on-surface-variant)' }}>chevron_left</span>
                  </button>
                  <h2 style={{ fontFamily: 'Sora, sans-serif', fontSize: '1.15rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.02em' }}>
                    {MONTHS[month]} {year}
                  </h2>
                  <button
                    onClick={nextMonth}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', borderRadius: '0.5rem' }}
                  >
                    <span className="material-icons-round" style={{ color: 'var(--on-surface-variant)' }}>chevron_right</span>
                  </button>
                </div>

                <ViewToggle viewMode={viewMode} onChange={(m) => {
                  setViewMode(m)
                  if (m === 'today') {
                    const now = new Date()
                    setYear(now.getFullYear()); setMonth(now.getMonth())
                    setSelectedDate(now.toISOString().slice(0, 10))
                    setViewMode('month')
                  }
                }} />
              </div>

              <CalendarGrid
                year={year}
                month={month}
                exams={exams}
                selectedDate={selectedDate}
                onSelect={setSelectedDate}
              />

              {/* Legend (SCRUM-93) */}
              <div style={{ display: 'flex', gap: '1.5rem', marginTop: '1.25rem', flexWrap: 'wrap' }}>
                <LegendItem color="rgba(59,130,246,0.3)" label="Exam scheduled" />
                <LegendItem color="rgba(186,26,26,0.3)"  label="Conflict detected" />
                <LegendItem color="var(--gradient-primary)" label="Today" />
              </div>
            </div>

            {/* ── Detail sidebar ─────────────────────────────────────────── */}
            <div className="card" style={{ minHeight: '500px', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 }}>
              <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--outline-variant)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.9rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.01em' }}>
                  Exam Details
                </h3>
                {selectedDate && (
                  <button onClick={() => setSelectedDate(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                    <span className="material-icons-round" style={{ color: 'var(--outline)', fontSize: '1rem' }}>close</span>
                  </button>
                )}
              </div>
              <ExamDetailSidebar date={selectedDate} exams={selectedExams} />
            </div>
          </>
        )}
      </div>
    </PageShell>
  )
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function LegendItem({ color, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
      <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: color, flexShrink: 0 }} />
      <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>{label}</span>
    </div>
  )
}

function ViewToggle({ viewMode, onChange }) {
  return (
    <div style={{ display: 'flex', gap: '0.25rem', padding: '0.25rem', background: 'var(--surface-container)', borderRadius: '9999px' }}>
      {[
        { key: 'today', label: 'Today' },
        { key: 'month', label: 'Month' },
        { key: 'list',  label: 'List'  },
      ].map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            padding: '0.35rem 0.875rem',
            borderRadius: '9999px',
            border: 'none',
            background: viewMode === key ? 'white' : 'transparent',
            boxShadow: viewMode === key ? 'var(--glass-shadow)' : 'none',
            fontFamily: 'Sora, sans-serif',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: viewMode === key ? 'var(--primary)' : 'var(--on-surface-variant)',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
