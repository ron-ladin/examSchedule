/**
 * SCRUM-84 — CourseAccordion: drill-down course list per programme.
 *
 * Props:
 *   selectedPrograms  string[]   — IDs of selected programmes (from ProgrammePanel)
 *   programmes        Array<{id, name, courseCount}> — full programme list
 *   toast             (msg, type) => void
 */

import { useState, useCallback, useEffect } from 'react'
import { api, ApiError } from '../api/client'
import { SEMESTER_LABELS, EVAL_TYPE } from '../models/types'
import { colorFor } from '../utils/progColor'

const EVAL_CHIP = {
  [EVAL_TYPE.Exam]:       { label: 'Exam',       bg: 'rgba(59,130,246,0.12)',  color: '#2563eb' },
  [EVAL_TYPE.Project]:    { label: 'Project',    bg: 'rgba(139,92,246,0.12)', color: '#7c3aed' },
  [EVAL_TYPE.Attendance]: { label: 'Attend',     bg: 'rgba(16,185,129,0.12)', color: '#059669' },
}

function EvalBadge({ type }) {
  const cfg = EVAL_CHIP[type] ?? { label: type, bg: 'rgba(114,119,133,0.12)', color: 'var(--outline)' }
  return (
    <span
      className="chip"
      style={{ background: cfg.bg, color: cfg.color, fontSize: '0.62rem', padding: '0.15rem 0.5rem' }}
    >
      {cfg.label}
    </span>
  )
}

function CourseRow({ course }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.65rem 0.875rem',
        borderRadius: '0.5rem',
        background: 'var(--surface-container-low)',
        border: '1px solid var(--outline-variant)',
      }}
    >
      <span
        className="mono"
        style={{ fontSize: '0.68rem', color: 'var(--outline)', minWidth: '3.5rem', flexShrink: 0 }}
      >
        {course.id}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: '0.82rem',
            fontWeight: 600,
            color: 'var(--on-surface)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {course.name}
        </p>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.7rem', color: 'var(--outline)', marginTop: '0.05rem' }}>
          {course.instructor}
        </p>
      </div>
      <EvalBadge type={course.evaluationType} />
    </div>
  )
}

function ProgrammeItem({ programme, isSelected, isOpen, onToggle, courses, loading, toast }) {
  const color = colorFor(programme.id)

  return (
    <div
      style={{
        borderRadius: '0.875rem',
        border: `1.5px solid ${isOpen ? color + '44' : 'var(--outline-variant)'}`,
        background: isOpen
          ? color + '08'
          : 'var(--surface-container-lowest)',
        overflow: 'hidden',
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      {/* Header row */}
      <button
        onClick={onToggle}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.875rem 1rem',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <div
          style={{
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            background: isSelected ? color : 'var(--outline-variant)',
            flexShrink: 0,
            transition: 'background 0.15s',
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.88rem',
              fontWeight: 700,
              color: 'var(--on-surface)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {programme.name}
          </p>
          <p
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.68rem',
              color: 'var(--outline)',
              marginTop: '0.1rem',
            }}
          >
            {programme.id} · {programme.courseCount ?? '—'} courses
          </p>
        </div>
        {!isSelected && (
          <span
            className="chip"
            style={{ background: 'rgba(114,119,133,0.1)', color: 'var(--outline)', fontSize: '0.6rem' }}
          >
            Not included
          </span>
        )}
        <span
          className="material-icons-round"
          style={{
            fontSize: '1.1rem',
            color: 'var(--on-surface-variant)',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0)',
            transition: 'transform 0.2s',
            flexShrink: 0,
          }}
        >
          expand_more
        </span>
      </button>

      {/* Expanded body */}
      {isOpen && (
        <div style={{ padding: '0 1rem 1rem' }}>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', color: 'var(--outline)' }}>
              <span
                className="material-icons-round"
                style={{ fontSize: '1.1rem', animation: 'spin 1s linear infinite' }}
              >
                sync
              </span>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.8rem' }}>Loading courses...</span>
            </div>
          ) : courses.length === 0 ? (
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.8rem',
                color: 'var(--outline)',
                padding: '0.75rem 0',
                textAlign: 'center',
              }}
            >
              No courses found for this programme.
            </p>
          ) : (
            (() => {
              // Group by semester
              const bySem = {}
              courses.forEach(c => {
                const sem = c.offerings?.[0]?.semester ?? 'Unknown'
                if (!bySem[sem]) bySem[sem] = []
                bySem[sem].push(c)
              })
              return Object.entries(bySem).map(([sem, cs]) => (
                <div key={sem} style={{ marginBottom: '0.875rem' }}>
                  <p
                    style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.65rem',
                      color: 'var(--outline)',
                      letterSpacing: '0.06em',
                      marginBottom: '0.4rem',
                      paddingLeft: '0.25rem',
                    }}
                  >
                    {SEMESTER_LABELS[sem] ?? sem}
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    {cs.map(c => <CourseRow key={c.id} course={c} />)}
                  </div>
                </div>
              ))
            })()
          )}
        </div>
      )}
    </div>
  )
}

export default function CourseAccordion({ selectedPrograms = [], programmes = [], toast }) {
  const [openId,            setOpenId]           = useState(null)
  const [courseCache,       setCourseCache]      = useState({})   // programmeId → Course[]
  const [loadingId,         setLoadingId]        = useState(null)
  // Self-fetch when no programmes list is provided by the parent
  const [fetchedProgrammes, setFetchedProgrammes] = useState([])

  useEffect(() => {
    if (programmes.length > 0) return
    api.getProgrammes()
      .then(data => setFetchedProgrammes(data ?? []))
      .catch(() => {
        setFetchedProgrammes(
          Object.keys(MOCK_COURSES).map(id => ({ id, name: `Programme ${id}`, courseCount: null }))
        )
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const displayProgrammes = programmes.length > 0 ? programmes : fetchedProgrammes

  const handleToggle = useCallback(async (id) => {
    if (openId === id) { setOpenId(null); return }
    setOpenId(id)

    if (courseCache[id] !== undefined) return   // already fetched

    setLoadingId(id)
    try {
      const data = await api.getProgrammeCourses(id)
      setCourseCache(prev => ({ ...prev, [id]: data ?? [] }))
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Could not load courses (${err.status})`
        : 'Backend offline — using mock course data.'
      toast?.(msg, 'warning')
      setCourseCache(prev => ({ ...prev, [id]: MOCK_COURSES[id] ?? [] }))
    } finally {
      setLoadingId(null)
    }
  }, [openId, courseCache, toast])

  if (displayProgrammes.length === 0) {
    return (
      <div
        className="card"
        style={{ padding: '2rem', textAlign: 'center', color: 'var(--outline)' }}
      >
        <span className="material-icons-round" style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}>
          school
        </span>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem' }}>
          No programmes loaded yet. Upload <span className="mono" style={{ color: 'var(--primary)' }}>programs.txt</span> first.
        </p>
      </div>
    )
  }

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
          Course Drill-Down
        </h3>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', marginTop: '0.15rem' }}>
          Expand a programme to see its courses and semesters.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {displayProgrammes.map(prog => (
          <ProgrammeItem
            key={prog.id}
            programme={prog}
            isSelected={selectedPrograms.includes(prog.id)}
            isOpen={openId === prog.id}
            onToggle={() => handleToggle(prog.id)}
            courses={courseCache[prog.id] ?? []}
            loading={loadingId === prog.id}
            toast={toast}
          />
        ))}
      </div>
    </div>
  )
}

// ── Mock fallback when backend is offline ──────────────────────────────────
const MOCK_COURSES = {
  '83101': [
    { id: '10101', name: 'Introduction to Computer Science', instructor: 'Prof. A. Cohen',  evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '10102', name: 'Discrete Mathematics',            instructor: 'Dr. M. Levy',     evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '10201', name: 'Data Structures',                 instructor: 'Dr. E. Golan',    evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '10202', name: 'Algorithms',                      instructor: 'Prof. R. Chen',   evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '10301', name: 'Software Engineering Project',    instructor: 'Dr. S. Bar',      evaluationType: 'Project', offerings: [{ programId: '83101', year: 3, semester: 'FALL', requirement: 'Obligatory' }] },
  ],
  '83201': [
    { id: '20101', name: 'Calculus 1',        instructor: 'Prof. O. Some', evaluationType: 'Exam',    offerings: [{ programId: '83201', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '20102', name: 'Linear Algebra',    instructor: 'Dr. Y. Klein',  evaluationType: 'Exam',    offerings: [{ programId: '83201', year: 1, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '20201', name: 'Calculus 2',        instructor: 'Prof. O. Some', evaluationType: 'Exam',    offerings: [{ programId: '83201', year: 2, semester: 'FALL', requirement: 'Obligatory' }] },
  ],
  '83301': [
    { id: '30101', name: 'Object-Oriented Programming', instructor: 'Dr. N. Cohen',  evaluationType: 'Exam',        offerings: [{ programId: '83301', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '30201', name: 'Database Systems',            instructor: 'Prof. B. Tal',  evaluationType: 'Exam',        offerings: [{ programId: '83301', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '30301', name: 'Capstone Project',            instructor: 'Dr. T. Rosen',  evaluationType: 'Project',     offerings: [{ programId: '83301', year: 3, semester: 'SUMM', requirement: 'Obligatory' }] },
  ],
  '83401': [
    { id: '40101', name: 'Information Systems Intro',   instructor: 'Prof. A. Ben',  evaluationType: 'Exam',        offerings: [{ programId: '83401', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '40201', name: 'Business Intelligence',       instructor: 'Dr. K. Alon',   evaluationType: 'Exam',        offerings: [{ programId: '83401', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
  ],
  '83501': [
    { id: '50101', name: 'Statistics for DS',    instructor: 'Prof. L. Dana', evaluationType: 'Exam',        offerings: [{ programId: '83501', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '50201', name: 'Machine Learning',     instructor: 'Dr. V. Oren',   evaluationType: 'Exam',        offerings: [{ programId: '83501', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '50202', name: 'Deep Learning Lab',    instructor: 'Dr. V. Oren',   evaluationType: 'Attendance',  offerings: [{ programId: '83501', year: 2, semester: 'SPRI', requirement: 'Elective' }] },
  ],
  '83601': [
    { id: '60101', name: 'Circuit Theory',      instructor: 'Prof. E. Shir', evaluationType: 'Exam',        offerings: [{ programId: '83601', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '60201', name: 'Signals & Systems',   instructor: 'Dr. Y. Ron',    evaluationType: 'Exam',        offerings: [{ programId: '83601', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
  ],
}
