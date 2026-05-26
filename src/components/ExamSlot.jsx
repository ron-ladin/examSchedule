/**
 * SCRUM-90 — ExamSlot: reusable exam card with programme colour coding.
 *
 * Props:
 *   exam      ExamAssignment — courseId, courseName, instructor, date, conflicts,
 *                              and optionally: time, room, proctors, programId
 *   size      'compact' | 'full'   (default 'full')
 *   onClick   () => void           optional
 */
import { colorFor } from '../utils/progColor'

export default function ExamSlot({ exam, size = 'full', onClick }) {
  // Derive colour from programId if available, else hash the courseId prefix
  const color       = colorFor(exam.programId ?? exam.courseId.slice(0, 3))
  const hasConflict = (exam.conflicts ?? 0) > 0

  // ── Compact variant: tiny pill used inside calendar cells ─────────────────
  if (size === 'compact') {
    return (
      <div
        onClick={onClick}
        style={{
          borderRadius: '3px',
          padding: '1px 5px',
          marginBottom: '2px',
          background: hasConflict ? 'rgba(186,26,26,0.15)' : `${color}1a`,
          borderLeft: `2.5px solid ${hasConflict ? '#ba1a1a' : color}`,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '0.6rem',
          color: hasConflict ? '#ba1a1a' : color,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          letterSpacing: '0.02em',
          cursor: onClick ? 'pointer' : 'default',
        }}
      >
        {exam.courseId}
      </div>
    )
  }

  // ── Full variant: card with coloured left stripe ───────────────────────────
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        borderRadius: '0.875rem',
        border: '1px solid',
        borderColor: hasConflict ? 'rgba(186,26,26,0.3)' : 'var(--outline-variant)',
        background: hasConflict
          ? 'rgba(186,26,26,0.04)'
          : 'var(--surface-container-lowest)',
        overflow: 'hidden',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.15s',
      }}
    >
      {/* Programme colour stripe */}
      <div style={{ width: '4px', background: hasConflict ? '#ba1a1a' : color, flexShrink: 0 }} />

      <div style={{ flex: 1, padding: '1rem 1.125rem', minWidth: 0 }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
          <div style={{ minWidth: 0 }}>
            <span
              className="mono"
              style={{ fontSize: '0.68rem', color, fontWeight: 600, display: 'block' }}
            >
              {exam.courseId}
            </span>
            <h4
              style={{
                fontFamily: 'Sora, sans-serif',
                fontSize: '0.88rem',
                fontWeight: 700,
                color: 'var(--on-surface)',
                marginTop: '0.1rem',
                letterSpacing: '-0.01em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {exam.courseName}
            </h4>
          </div>
          {hasConflict && (
            <span className="chip chip-red" style={{ fontSize: '0.6rem', flexShrink: 0, marginLeft: '0.5rem' }}>
              {exam.conflicts} Conflict{exam.conflicts > 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Detail rows */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          {[
            exam.instructor && { icon: 'person',      text: exam.instructor           },
            exam.time       && { icon: 'schedule',    text: exam.time                  },
            exam.room       && { icon: 'location_on', text: exam.room                  },
            exam.proctors?.length && {
              icon: 'people',
              text: Array.isArray(exam.proctors) ? exam.proctors.join(', ') : exam.proctors,
            },
          ].filter(Boolean).map(row => (
            <div key={row.icon} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.4rem' }}>
              <span
                className="material-symbols-outlined"
                style={{ fontSize: '0.85rem', color: 'var(--outline)', marginTop: '1px', flexShrink: 0 }}
              >
                {row.icon}
              </span>
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', lineHeight: 1.4 }}>
                {row.text}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
