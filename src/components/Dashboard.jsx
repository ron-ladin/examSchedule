/**
 * Dashboard.jsx
 * Source: Stitch screen "Data Input Dashboard - English"
 * Design freeze: Sora font · Liquid Glass · Electric Blue→Deep Purple gradient
 *
 * Upload zone binding (Python file readers):
 *   courses  slot → courses.txt  → src/adapters/readers/course_file_reader.py
 *   dates    slot → dates.txt    → src/adapters/readers/exam_period_file_reader.py
 *   programs slot → programs.txt → src/adapters/readers/program_selector_reader.py
 *
 * Placeholders embedded below (grep "PLACEHOLDER"):
 *   - Manual Entry Drawer   → <ManualEntryDrawer /> (to be implemented)
 *   - Settings Panel        → <SettingsPanel />      (to be implemented)
 */

import { useState, useRef, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useScheduler } from '../hooks/useScheduler'
import { useToast } from '../hooks/useToast'
import { ToastContainer } from './Toast'
import { api, ApiError } from '../api/client'
import { DATA_FILES } from '../models/types'

// ── Sidebar navigation items ───────────────────────────────────────────────
const NAV_ITEMS = [
  { icon: 'dashboard',       label: 'Dashboard',      path: '/dashboard',  active: true  },
  { icon: 'calendar_today',  label: 'Schedules',      path: '/results',    active: false },
  { icon: 'auto_fix_high',   label: 'Conflict Solver',path: '/calendar',   active: false },
  { icon: 'history',         label: 'History',        path: '#',           active: false },
  { icon: 'settings',        label: 'Settings',       path: '#settings',   active: false },
]

// ── Upload card config — keyed to Python file readers ─────────────────────
const UPLOAD_CARDS = [
  {
    key:       'courses',
    icon:      'inventory_2',
    title:     'Courses Inventory',
    desc:      'Upload your courses list with program offerings, instructors, and evaluation types.',
    fileName:  DATA_FILES.COURSES,    // courses.txt → course_file_reader.py
    accept:    '.txt,.csv',
    format:    'TXT · CSV',
  },
  {
    key:       'dates',
    icon:      'date_range',
    title:     'Exam Periods',
    desc:      'Upload the exam window definitions — semester dates, moedim ranges, and exclusions.',
    fileName:  DATA_FILES.DATES,      // dates.txt → exam_period_file_reader.py
    accept:    '.txt,.csv',
    format:    'TXT · CSV',
  },
  {
    key:       'programs',
    icon:      'group',
    title:     'Program Selection',
    desc:      'Upload the list of program IDs to include in this scheduling run.',
    fileName:  DATA_FILES.PROGRAMS,   // programs.txt → program_selector_reader.py
    accept:    '.txt,.csv',
    format:    'TXT · CSV',
  },
]

// ── Sub-components ─────────────────────────────────────────────────────────

function Sidebar({ settingsOpen, onSettingsToggle }) {
  return (
    <aside
      style={{
        width: '240px',
        flexShrink: 0,
        background: 'var(--surface-container-lowest)',
        borderRight: '1px solid var(--outline-variant)',
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem 1rem',
        minHeight: '100vh',
        position: 'sticky',
        top: 0,
      }}
    >
      {/* Logo */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0 0.5rem',
          marginBottom: '2rem',
        }}
      >
        <div
          style={{
            width: '30px',
            height: '30px',
            borderRadius: '8px',
            background: 'var(--gradient-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span className="material-icons-round" style={{ color: 'white', fontSize: '1rem' }}>
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

      {/* Nav items */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', flex: 1 }}>
        {NAV_ITEMS.map(item => (
          item.path === '#settings' ? (
            <button
              key={item.label}
              onClick={onSettingsToggle}
              className={`sidebar-item${settingsOpen ? ' active' : ''}`}
              style={{ border: 'none', width: '100%', textAlign: 'left' }}
            >
              <span className="material-icons-round">{item.icon}</span>
              {item.label}
            </button>
          ) : (
            <Link
              key={item.label}
              to={item.path}
              className={`sidebar-item${item.active ? ' active' : ''}`}
            >
              <span className="material-icons-round">{item.icon}</span>
              {item.label}
            </Link>
          )
        ))}
      </nav>

      {/* System status */}
      <div
        style={{
          padding: '0.75rem 1rem',
          borderRadius: '0.75rem',
          background: 'var(--surface-container)',
          marginTop: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <div
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: 'var(--success)',
            }}
          />
          <span
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.65rem',
              color: 'var(--on-surface-variant)',
              letterSpacing: '0.04em',
            }}
          >
            SYSTEM OPTIMAL
          </span>
        </div>
        <span
          style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.7rem',
            color: 'var(--outline)',
          }}
        >
          AI Engine v4.2.0 Online
        </span>
      </div>
    </aside>
  )
}

function TopBar() {
  return (
    <header
      style={{
        height: '64px',
        borderBottom: '1px solid var(--outline-variant)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 2rem',
        background: 'var(--surface-container-lowest)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <div>
        <h1
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: '1.1rem',
            fontWeight: 700,
            color: 'var(--on-surface)',
            letterSpacing: '-0.02em',
          }}
        >
          Dashboard
        </h1>
        <p
          style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.75rem',
            color: 'var(--on-surface-variant)',
          }}
        >
          Initialize a new scheduling session
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '0.5rem',
            borderRadius: '0.5rem',
          }}
        >
          <span className="material-icons-round" style={{ color: 'var(--on-surface-variant)', fontSize: '1.3rem' }}>
            notifications_none
          </span>
        </button>

        {/* User avatar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '50%',
              background: 'var(--gradient-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.8rem',
              fontWeight: 700,
              color: 'white',
            }}
          >
            AT
          </div>
          <div>
            <p
              style={{
                fontFamily: 'Sora, sans-serif',
                fontSize: '0.8rem',
                fontWeight: 600,
                color: 'var(--on-surface)',
              }}
            >
              Dr. Aris Thorne
            </p>
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.7rem',
                color: 'var(--on-surface-variant)',
              }}
            >
              Exam Coordinator
            </p>
          </div>
        </div>

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
      </div>
    </header>
  )
}

function UploadCard({ card, file, uploading, onFileSelect, isDragOver, onDragOver, onDragLeave, onDrop }) {
  const inputRef = useRef(null)

  return (
    <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Card header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: file
              ? 'rgba(16,185,129,0.1)'
              : 'linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            border: '1px solid',
            borderColor: file ? 'rgba(16,185,129,0.2)' : 'var(--outline-variant)',
          }}
        >
          <span
            className="material-icons-round"
            style={{
              fontSize: '1.25rem',
              color: file ? 'var(--success)' : 'var(--primary)',
            }}
          >
            {file ? 'check_circle' : card.icon}
          </span>
        </div>
        <div>
          <h3
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.95rem',
              fontWeight: 700,
              color: 'var(--on-surface)',
              marginBottom: '0.2rem',
              letterSpacing: '-0.01em',
            }}
          >
            {card.title}
          </h3>
          <p
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8rem',
              color: 'var(--on-surface-variant)',
              lineHeight: 1.5,
            }}
          >
            {card.desc}
          </p>
        </div>
      </div>

      {/* Upload zone */}
      <div
        className={`upload-zone${isDragOver ? ' drag-over' : ''}${file ? ' has-file' : ''}`}
        style={{ padding: '1.5rem', textAlign: 'center' }}
        onClick={() => inputRef.current?.click()}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={card.accept}
          style={{ display: 'none' }}
          onChange={e => e.target.files[0] && onFileSelect(e.target.files[0])}
        />

        {uploading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <span className="material-icons-round" style={{ color: 'var(--primary)', fontSize: '1.1rem', animation: 'spin 1s linear infinite' }}>
              sync
            </span>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', color: 'var(--primary)' }}>
              Uploading...
            </span>
          </div>
        ) : file ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <span className="material-icons-round" style={{ color: 'var(--success)', fontSize: '1.1rem' }}>
              insert_drive_file
            </span>
            <span
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.8rem',
                color: 'var(--success)',
                fontWeight: 500,
              }}
            >
              {file.name}
            </span>
            <button
              onClick={e => { e.stopPropagation(); onFileSelect(null) }}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '0',
                lineHeight: 1,
              }}
            >
              <span className="material-icons-round" style={{ color: 'var(--outline)', fontSize: '1rem' }}>
                close
              </span>
            </button>
          </div>
        ) : (
          <>
            <span
              className="material-icons-round"
              style={{ color: 'var(--outline)', fontSize: '1.75rem', display: 'block', marginBottom: '0.5rem' }}
            >
              cloud_upload
            </span>
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.8rem',
                color: 'var(--on-surface-variant)',
                marginBottom: '0.25rem',
              }}
            >
              Drop <span className="mono" style={{ color: 'var(--primary)', fontWeight: 500 }}>{card.fileName}</span> here
            </p>
            <p
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.65rem',
                color: 'var(--outline)',
                letterSpacing: '0.04em',
              }}
            >
              {card.format}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PLACEHOLDER: Manual Entry Drawer
// Replace this comment block with <ManualEntryDrawer /> when implementing.
// The drawer should slide in from the right and expose a form that creates
// Course records equivalent to a parsed courses.txt row:
//   { id, name, instructor, evaluationType, offerings: [{ programId, year, semester, requirement }] }
// Completed entries should be appended to the 'manualCourses' state in useScheduler.
// ─────────────────────────────────────────────────────────────────────────────
function ManualEntryDrawerPlaceholder({ open, onClose }) {
  if (!open) return null
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <div
        style={{ flex: 1, background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
      />
      <aside
        className="glass-light"
        style={{
          width: '420px',
          padding: '2rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.5rem',
          overflowY: 'auto',
          borderLeft: '1px solid var(--outline-variant)',
          borderRadius: 0,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '1.1rem',
              fontWeight: 700,
              color: 'var(--on-surface)',
              letterSpacing: '-0.02em',
            }}
          >
            Add Course Manually
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <span className="material-icons-round" style={{ color: 'var(--outline)' }}>close</span>
          </button>
        </div>

        {/* PLACEHOLDER — form fields to be implemented */}
        <div
          style={{
            padding: '2rem',
            borderRadius: '1rem',
            background: 'var(--surface-container)',
            textAlign: 'center',
            border: '2px dashed var(--outline-variant)',
          }}
        >
          <span className="material-icons-round" style={{ color: 'var(--outline)', fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}>
            edit_note
          </span>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', color: 'var(--on-surface-variant)' }}>
            Manual Entry form — to be implemented
          </p>
          <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'var(--outline)', marginTop: '0.5rem' }}>
            Fields: id · name · instructor · evaluationType · offerings[]
          </p>
        </div>
      </aside>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PLACEHOLDER: Settings Panel
// Replace this comment block with <SettingsPanel /> when implementing.
// Settings to expose (aligned with ExamPeriod & AppController config):
//   1. Rest Days toggle  — array of weekday indices (0=Sun … 6=Sat)
//      Populates ExamPeriod._is_excluded_date() logic on the backend.
//   2. Holiday Upload    — date range picker or file upload for excluded_dates
//      Appended to ExamPeriod.excluded_dates before generation.
//   3. Min Gap Days      — minimum study gap enforced by ScheduleGenerator
//   4. Prefer Early Moed — prioritize Aleph before Bet in sorting
// ─────────────────────────────────────────────────────────────────────────────
function SettingsPanelPlaceholder({ open, onClose, settings, updateSetting }) {
  if (!open) return null

  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  const toggleRestDay = (idx) => {
    const current = settings.restDays || []
    const updated = current.includes(idx)
      ? current.filter(d => d !== idx)
      : [...current, idx]
    updateSetting('restDays', updated)
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <div
        style={{ flex: 1, background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
      />
      <aside
        className="glass-light"
        style={{
          width: '380px',
          padding: '2rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.5rem',
          overflowY: 'auto',
          borderLeft: '1px solid var(--outline-variant)',
          borderRadius: 0,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '1.1rem',
              fontWeight: 700,
              color: 'var(--on-surface)',
              letterSpacing: '-0.02em',
            }}
          >
            Settings
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <span className="material-icons-round" style={{ color: 'var(--outline)' }}>close</span>
          </button>
        </div>

        {/* Rest Days toggle */}
        <div>
          <h3
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: 'var(--on-surface)',
              marginBottom: '0.75rem',
            }}
          >
            Rest Days
          </h3>
          <p
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8rem',
              color: 'var(--on-surface-variant)',
              marginBottom: '0.875rem',
              lineHeight: 1.5,
            }}
          >
            Toggle days on which exams cannot be scheduled.
            Populates <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>ExamPeriod.excluded_dates</span>.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {DAYS.map((day, idx) => {
              const isRest = (settings.restDays || []).includes(idx)
              return (
                <button
                  key={day}
                  onClick={() => toggleRestDay(idx)}
                  style={{
                    padding: '0.4rem 0.75rem',
                    borderRadius: '9999px',
                    border: '1.5px solid',
                    borderColor: isRest ? 'var(--secondary)' : 'var(--outline-variant)',
                    background: isRest
                      ? 'linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))'
                      : 'transparent',
                    fontFamily: 'Sora, sans-serif',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    color: isRest ? 'var(--secondary)' : 'var(--on-surface-variant)',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  {day}
                </button>
              )
            })}
          </div>
        </div>

        {/* Holiday upload — PLACEHOLDER */}
        <div>
          <h3
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: 'var(--on-surface)',
              marginBottom: '0.75rem',
            }}
          >
            Holiday Exclusions
          </h3>
          <p
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.8rem',
              color: 'var(--on-surface-variant)',
              marginBottom: '0.875rem',
              lineHeight: 1.5,
            }}
          >
            Upload a list of holiday dates to exclude from all exam periods.
            Merged into <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>ExamPeriod.excluded_dates</span>.
          </p>
          {/* PLACEHOLDER — holiday file upload or date picker to be implemented */}
          <div
            className="upload-zone"
            style={{ padding: '1.25rem', textAlign: 'center' }}
          >
            <span
              className="material-icons-round"
              style={{ color: 'var(--outline)', fontSize: '1.5rem', display: 'block', marginBottom: '0.4rem' }}
            >
              event_busy
            </span>
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.78rem',
                color: 'var(--on-surface-variant)',
              }}
            >
              Holiday list upload — to be implemented
            </p>
          </div>
        </div>

        {/* Min gap days */}
        <div>
          <h3
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: 'var(--on-surface)',
              marginBottom: '0.5rem',
            }}
          >
            Minimum Study Gap
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <input
              type="range"
              min={0}
              max={7}
              value={settings.minGapDays ?? 1}
              onChange={e => updateSetting('minGapDays', Number(e.target.value))}
              style={{ flex: 1, accentColor: 'var(--primary)' }}
            />
            <span
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.9rem',
                fontWeight: 600,
                color: 'var(--primary)',
                minWidth: '2rem',
                textAlign: 'right',
              }}
            >
              {settings.minGapDays ?? 1}d
            </span>
          </div>
          <p
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.75rem',
              color: 'var(--outline)',
              marginTop: '0.25rem',
            }}
          >
            Days enforced between consecutive exams for the same student group
          </p>
        </div>
      </aside>
    </div>
  )
}

// ── Upload helpers keyed to API calls ─────────────────────────────────────
const UPLOAD_FN = {
  courses:  (file) => api.uploadCourses(file),
  dates:    (file) => api.uploadPeriods(file),
  programs: (file) => Promise.resolve({ message: 'Programs file stored locally.' }),
}

// ── Main component ─────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate()
  const { files, setFile, settings, updateSetting, isReadyToGenerate, startProcessing } = useScheduler()
  const { toasts, toast, dismiss } = useToast()

  const [manualEntryOpen, setManualEntryOpen] = useState(false)
  const [settingsOpen,     setSettingsOpen]    = useState(false)
  const [dragOver,         setDragOver]        = useState({})
  const [uploading,        setUploading]       = useState({})

  const handleDragOver  = useCallback((key, e) => { e.preventDefault(); setDragOver(p => ({ ...p, [key]: true }))  }, [])
  const handleDragLeave = useCallback((key)    => { setDragOver(p => ({ ...p, [key]: false }))                      }, [])

  const handleDrop = useCallback((key, e) => {
    e.preventDefault()
    setDragOver(p => ({ ...p, [key]: false }))
    const dropped = e.dataTransfer.files[0]
    if (dropped) handleFileSelect(key, dropped)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleFileSelect = useCallback(async (key, file) => {
    if (!file) { setFile(key, null); return }
    setFile(key, file)
    setUploading(p => ({ ...p, [key]: true }))
    try {
      await UPLOAD_FN[key](file)
      toast(`${file.name} uploaded successfully.`, 'success')
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Upload failed (${err.status}): ${err.message}`
        : 'Upload failed — backend may not be running.'
      toast(msg, 'warning')
    } finally {
      setUploading(p => ({ ...p, [key]: false }))
    }
  }, [setFile, toast])

  const handleGenerate = async () => {
    await startProcessing()
    navigate('/processing')
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--surface)' }}>
      <Sidebar settingsOpen={settingsOpen} onSettingsToggle={() => setSettingsOpen(true)} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TopBar />

        <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>

          {/* ── Session header ─────────────────────────────────────────── */}
          <div style={{ marginBottom: '2rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <h2
                  style={{
                    fontFamily: 'Sora, sans-serif',
                    fontSize: '1.4rem',
                    fontWeight: 700,
                    color: 'var(--on-surface)',
                    letterSpacing: '-0.02em',
                    marginBottom: '0.25rem',
                  }}
                >
                  Initialize Session
                </h2>
                <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>
                  Upload the three required data files to begin schedule generation.
                </p>
              </div>

              {/* Progress indicator */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {UPLOAD_CARDS.map(card => (
                  <div
                    key={card.key}
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: files[card.key]
                        ? 'var(--success)'
                        : 'var(--outline-variant)',
                      transition: 'background 0.2s',
                    }}
                  />
                ))}
                <span
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.7rem',
                    color: 'var(--on-surface-variant)',
                    marginLeft: '0.25rem',
                  }}
                >
                  {Object.values(files).filter(Boolean).length} / 3 uploaded
                </span>
              </div>
            </div>
          </div>

          {/* ── Upload cards ───────────────────────────────────────────── */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1.25rem',
              marginBottom: '2rem',
            }}
          >
            {UPLOAD_CARDS.map(card => (
              <UploadCard
                key={card.key}
                card={card}
                file={files[card.key]}
                uploading={uploading[card.key]}
                onFileSelect={f => handleFileSelect(card.key, f)}
                isDragOver={dragOver[card.key]}
                onDragOver={e  => handleDragOver(card.key, e)}
                onDragLeave={() => handleDragLeave(card.key)}
                onDrop={e      => handleDrop(card.key, e)}
              />
            ))}
          </div>

          {/* ── Action row ─────────────────────────────────────────────── */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              flexWrap: 'wrap',
              padding: '1.5rem',
              background: 'var(--surface-container-lowest)',
              border: '1px solid var(--outline-variant)',
              borderRadius: '1.25rem',
            }}
          >
            {/* Manual entry — PLACEHOLDER trigger */}
            <button
              className="btn-secondary"
              onClick={() => setManualEntryOpen(true)}
              style={{ gap: '0.4rem' }}
            >
              <span className="material-icons-round" style={{ fontSize: '1rem' }}>add</span>
              Add Course Manually
            </button>

            <div style={{ flex: 1 }} />

            {!isReadyToGenerate && (
              <p
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.8rem',
                  color: 'var(--outline)',
                }}
              >
                Upload all 3 files to enable generation
              </p>
            )}

            <button
              className="btn-primary"
              disabled={!isReadyToGenerate}
              onClick={handleGenerate}
              style={{
                opacity: isReadyToGenerate ? 1 : 0.45,
                cursor: isReadyToGenerate ? 'pointer' : 'not-allowed',
              }}
            >
              <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>auto_awesome</span>
              Generate Schedule
            </button>
          </div>

          {/* ── Info strip: file format reminder ─────────────────────── */}
          <div
            style={{
              marginTop: '1.5rem',
              padding: '1rem 1.25rem',
              borderRadius: '0.875rem',
              background: 'var(--surface-container)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
            }}
          >
            <span className="material-icons-round" style={{ color: 'var(--primary)', fontSize: '1.1rem', marginTop: '1px', flexShrink: 0 }}>
              info
            </span>
            <div>
              <p
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.8rem',
                  color: 'var(--on-surface)',
                  marginBottom: '0.25rem',
                  fontWeight: 500,
                }}
              >
                Expected file format
              </p>
              <p
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.75rem',
                  color: 'var(--on-surface-variant)',
                  lineHeight: 1.6,
                }}
              >
                <strong>courses.txt</strong> — delimited by <code>$$$$</code> · fields: name, id, instructor, offerings, eval_type<br />
                <strong>dates.txt</strong> — semester / moed / date ranges / excluded dates<br />
                <strong>programs.txt</strong> — one program ID per line (e.g. 83101)
              </p>
            </div>
          </div>
        </main>

        {/* ── Footer ───────────────────────────────────────────────────── */}
        <footer
          style={{
            padding: '1rem 2rem',
            borderTop: '1px solid var(--outline-variant)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--surface-container-lowest)',
          }}
        >
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'var(--outline)' }}>
            © 2024 Syncademic Labs
          </span>
          <div style={{ display: 'flex', gap: '1.5rem' }}>
            {['Security Protocol', 'Privacy Policy', 'API Docs'].map(l => (
              <a
                key={l}
                href="#"
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.75rem',
                  color: 'var(--outline)',
                  textDecoration: 'none',
                }}
              >
                {l}
              </a>
            ))}
          </div>
        </footer>
      </div>

      {/* ── PLACEHOLDER: Manual Entry Drawer ─────────────────────────────── */}
      <ManualEntryDrawerPlaceholder
        open={manualEntryOpen}
        onClose={() => setManualEntryOpen(false)}
      />

      {/* ── PLACEHOLDER: Settings Panel ──────────────────────────────────── */}
      <SettingsPanelPlaceholder
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        updateSetting={updateSetting}
      />

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}
