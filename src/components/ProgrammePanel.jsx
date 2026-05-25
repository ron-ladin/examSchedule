/**
 * SCRUM-83 — Programme multi-select panel.
 * Fetches GET /api/programmes, lets the user toggle which programmes
 * are included in this scheduling run.
 *
 * Props:
 *   selected   string[]        — array of selected programme IDs
 *   onChange   (ids: string[]) => void
 *   toast      (msg, type) => void  — from useToast
 */

import { useState, useEffect } from 'react'
import { api, ApiError } from '../api/client'
import { colorFor } from '../utils/progColor'

export default function ProgrammePanel({ selected = [], onChange, toast }) {
  const [programmes, setProgrammes] = useState([])
  const [loading,    setLoading]    = useState(true)
  const [search,     setSearch]     = useState('')

  useEffect(() => {
    let cancelled = false
    api.getProgrammes()
      .then(data => { if (!cancelled) setProgrammes(data ?? []) })
      .catch(err => {
        if (cancelled) return
        const msg = err instanceof ApiError
          ? `Could not load programmes (${err.status})`
          : 'Backend offline — programme list unavailable.'
        toast?.(msg, 'warning')
        setProgrammes(MOCK_PROGRAMMES)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = programmes.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.id.toLowerCase().includes(search.toLowerCase())
  )

  const toggle = (id) => {
    onChange(
      selected.includes(id) ? selected.filter(s => s !== id) : [...selected, id]
    )
  }

  const toggleAll = () => {
    onChange(selected.length === programmes.length ? [] : programmes.map(p => p.id))
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.95rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '-0.01em' }}>
            Programme Selection
          </h3>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--on-surface-variant)', marginTop: '0.15rem' }}>
            {selected.length} of {programmes.length} selected
          </p>
        </div>
        <button
          onClick={toggleAll}
          style={{
            fontFamily: 'Sora, sans-serif', fontSize: '0.75rem', fontWeight: 600,
            color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', padding: 0,
          }}
        >
          {selected.length === programmes.length ? 'Deselect All' : 'Select All'}
        </button>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: '1rem' }}>
        <span
          className="material-icons-round"
          style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--outline)', fontSize: '1rem', pointerEvents: 'none' }}
        >
          search
        </span>
        <input
          type="text"
          placeholder="Search programmes..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            width: '100%',
            padding: '0.55rem 1rem 0.55rem 2.25rem',
            borderRadius: '0.65rem',
            border: '1.5px solid var(--outline-variant)',
            background: 'var(--surface-container-low)',
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.83rem',
            color: 'var(--on-surface)',
            outline: 'none',
          }}
        />
      </div>

      {/* List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '340px', overflowY: 'auto' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--outline)' }}>
            <span className="material-icons-round" style={{ fontSize: '1.5rem', animation: 'spin 1s linear infinite' }}>sync</span>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', marginTop: '0.5rem' }}>Loading programmes...</p>
          </div>
        ) : filtered.length === 0 ? (
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: 'var(--outline)', textAlign: 'center', padding: '1.5rem' }}>
            No programmes match &quot;{search}&quot;
          </p>
        ) : (
          filtered.map(prog => {
            const isSelected = selected.includes(prog.id)
            const color = colorFor(prog.id)
            return (
              <button
                key={prog.id}
                onClick={() => toggle(prog.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.65rem 0.75rem',
                  borderRadius: '0.65rem',
                  border: `1.5px solid ${isSelected ? color + '44' : 'var(--outline-variant)'}`,
                  background: isSelected ? color + '12' : 'transparent',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                  width: '100%',
                }}
              >
                {/* Colour dot */}
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: isSelected ? color : 'var(--outline-variant)', flexShrink: 0, transition: 'background 0.15s' }} />

                {/* Programme info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontFamily: 'Sora, sans-serif', fontSize: '0.83rem', fontWeight: 600, color: 'var(--on-surface)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {prog.name}
                  </p>
                  <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.68rem', color: 'var(--outline)', marginTop: '0.1rem' }}>
                    {prog.id} · {prog.courseCount ?? '—'} courses
                  </p>
                </div>

                {/* Checkbox */}
                <span className="material-icons-round" style={{ fontSize: '1.1rem', color: isSelected ? color : 'var(--outline-variant)', transition: 'color 0.15s' }}>
                  {isSelected ? 'check_box' : 'check_box_outline_blank'}
                </span>
              </button>
            )
          })
        )}
      </div>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div style={{ borderTop: '1px solid var(--outline-variant)', marginTop: '1rem', paddingTop: '0.875rem' }}>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.72rem', color: 'var(--outline)', marginBottom: '0.5rem', letterSpacing: '0.02em' }}>
            INCLUDED IN THIS RUN
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
            {selected.map(id => {
              const prog = programmes.find(p => p.id === id)
              const color = colorFor(id)
              return (
                <span
                  key={id}
                  className="chip"
                  style={{ background: color + '18', color, border: `1px solid ${color}44`, fontSize: '0.68rem' }}
                >
                  {prog?.name ?? id}
                  <button
                    onClick={() => toggle(id)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color, lineHeight: 1, marginLeft: '0.2rem' }}
                  >
                    <span className="material-icons-round" style={{ fontSize: '0.8rem' }}>close</span>
                  </button>
                </span>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Mock fallback when backend is offline ──────────────────────────────────
const MOCK_PROGRAMMES = [
  { id: '83101', name: 'Computer Science',       courseCount: 42 },
  { id: '83201', name: 'Mathematics',            courseCount: 31 },
  { id: '83301', name: 'Software Engineering',   courseCount: 38 },
  { id: '83401', name: 'Information Systems',    courseCount: 27 },
  { id: '83501', name: 'Data Science',           courseCount: 24 },
  { id: '83601', name: 'Electrical Engineering', courseCount: 45 },
]
