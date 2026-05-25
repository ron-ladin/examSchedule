/**
 * SCRUM-91 — SemesterGroupLayout: exam list grouped by semester.
 *
 * Accepts a flat ExamAssignment[] and organises them into FALL / SPRI / SUMM
 * sections, sorted by date within each semester.
 *
 * Props:
 *   exams         ExamAssignment[]   — from Schedule.assignments
 *   onSelectExam  (exam) => void     — optional; called when user clicks a slot
 */
import ExamSlot from './ExamSlot'
import { SEMESTER_LABELS } from '../models/types'
import { StaggerList, StaggerItem } from './Motion'

function inferSemester(dateStr) {
  const m = new Date(dateStr + 'T00:00:00').getMonth()
  if (m >= 8 || m <= 1) return 'FALL'
  if (m >= 5 && m <= 7) return 'SUMM'
  return 'SPRI'
}

function formatDate(dateStr) {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

export default function SemesterGroupLayout({ exams = [], onSelectExam }) {
  const bySemester = {}
  for (const exam of exams) {
    const sem = exam.semester ?? inferSemester(exam.date)
    if (!bySemester[sem]) bySemester[sem] = []
    bySemester[sem].push(exam)
  }

  const order     = ['FALL', 'SPRI', 'SUMM']
  const semesters = order.filter(k => bySemester[k])

  if (semesters.length === 0) {
    return (
      <div style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--outline)' }}>
        <span
          className="material-icons-round"
          style={{ fontSize: '2.5rem', display: 'block', marginBottom: '0.75rem' }}
        >
          event_note
        </span>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.88rem' }}>
          No exams to display.
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
      {semesters.map(sem => {
        const semExams = bySemester[sem]
          .slice()
          .sort((a, b) => a.date.localeCompare(b.date))

        const semLabel = (SEMESTER_LABELS[sem] ?? sem).toUpperCase()

        return (
          <section key={sem}>
            {/* Section divider */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.875rem',
                marginBottom: '1.25rem',
              }}
            >
              <div style={{ flex: 1, height: '1px', background: 'var(--outline-variant)' }} />
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.35rem 1rem',
                  borderRadius: '9999px',
                  background: 'var(--surface-container)',
                  border: '1px solid var(--outline-variant)',
                }}
              >
                <span
                  className="material-icons-round"
                  style={{ fontSize: '0.9rem', color: 'var(--primary)' }}
                >
                  school
                </span>
                <span
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.65rem',
                    color: 'var(--on-surface-variant)',
                    letterSpacing: '0.06em',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {semLabel} · {semExams.length} EXAM{semExams.length !== 1 ? 'S' : ''}
                </span>
              </div>
              <div style={{ flex: 1, height: '1px', background: 'var(--outline-variant)' }} />
            </div>

            {/* Exam grid */}
            <StaggerList
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                gap: '0.875rem',
              }}
            >
              {semExams.map(exam => (
                <StaggerItem key={exam.courseId} style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <span
                    style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.62rem',
                      color: 'var(--outline)',
                      letterSpacing: '0.04em',
                      paddingLeft: '0.25rem',
                    }}
                  >
                    {formatDate(exam.date)}
                  </span>
                  <ExamSlot
                    exam={exam}
                    size="full"
                    onClick={onSelectExam ? () => onSelectExam(exam) : undefined}
                  />
                </StaggerItem>
              ))}
            </StaggerList>
          </section>
        )
      })}
    </div>
  )
}
