/**
 * ProcessingState.jsx
 * Source: Stitch screen "Algorithmic Processing - English"
 * Design freeze: Sora font · Liquid Glass · Electric Blue→Deep Purple gradient
 *
 * Mirrors AppController.run() pipeline stages:
 *   Step 1 — validate structural constraints
 *   Step 2 — build O(n²) conflict graph
 *   Step 3 — apply MCV heuristics
 *   Step 4 — execute CSP backtracking engine
 *
 * State is driven by useScheduler().processingState.
 * TODO: replace mock simulation with real SSE stream from /api/generate/stream
 */

import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useScheduler } from '../hooks/useScheduler'
import { PageShell } from './Motion'

function StepRow({ step, index, isCurrent }) {
  const statusIcon = {
    done:    { icon: 'check_circle',   color: '#10b981' },
    running: { icon: 'radio_button_checked', color: '#3b82f6' },
    pending: { icon: 'radio_button_unchecked', color: 'rgba(255,255,255,0.2)' },
    error:   { icon: 'error',          color: '#ba1a1a' },
  }[step.status]

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
        <span
          className="material-icons-round"
          style={{
            fontSize: '1.25rem',
            color: statusIcon.color,
            transition: 'color 0.3s',
          }}
        >
          {step.status === 'running'
            ? 'radio_button_checked'
            : statusIcon.icon}
        </span>
        {index < 3 && (
          <div
            style={{
              width: '2px',
              height: '36px',
              background:
                step.status === 'done'
                  ? 'var(--gradient-primary)'
                  : 'rgba(255,255,255,0.1)',
              transition: 'background 0.3s',
              marginTop: '2px',
            }}
          />
        )}
      </div>

      <div style={{ paddingTop: '2px', paddingBottom: index < 3 ? '1.25rem' : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <p
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '0.9rem',
              fontWeight: step.status === 'running' ? 700 : 500,
              color: step.status === 'pending' ? 'rgba(255,255,255,0.3)' : 'white',
              transition: 'color 0.3s',
              letterSpacing: '-0.01em',
            }}
          >
            {step.label}
          </p>
          {step.status === 'running' && (
            <span className="chip" style={{ background: 'rgba(59,130,246,0.2)', color: '#93c5fd', animation: 'pulse 1.5s infinite' }}>
              LIVE
            </span>
          )}
        </div>
        {step.elapsed !== null && (
          <p
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.7rem',
              color: 'rgba(255,255,255,0.35)',
              marginTop: '0.2rem',
              letterSpacing: '0.03em',
            }}
          >
            {step.elapsed.toFixed(2)}s elapsed
          </p>
        )}
      </div>
    </div>
  )
}

export default function ProcessingState() {
  const navigate = useNavigate()
  const { processingState, pauseProcessing, cancelProcessing, updateStep, appendLog, setResults } = useScheduler()
  const { isRunning, isPaused, progress, steps, engineLoad, logs } = processingState
  const logRef = useRef(null)

  /* ── Mock simulation — replace with SSE: /api/generate/stream ─── */
  useEffect(() => {
    if (!isRunning || isPaused) return
    const timings = [0.42, 1.18, 2.31, 4.85]
    let step = 0

    const tick = () => {
      if (step >= steps.length) {
        // TODO: replace mock results with actual API response
        setResults([
          { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 21, avgStudyGap: 3.2, resourceLoad: 'Moderate' },
          { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 14, avgStudyGap: 1.8, resourceLoad: 'Intense' },
          { periodKey: 'FALL - Aleph', assignments: [], totalConflicts: 0, durationDays: 28, avgStudyGap: 4.5, resourceLoad: 'Minimal' },
        ])
        navigate('/results')
        return
      }

      updateStep(step, { status: 'running' })
      appendLog(`[ENGINE] ${steps[step].label}`)

      setTimeout(() => {
        updateStep(step, { status: 'done', elapsed: timings[step] })
        appendLog(`[ENGINE] ✓ Step ${step + 1} complete in ${timings[step]}s`)
        step++
        if (step < steps.length) {
          setTimeout(tick, 600)
        } else {
          setTimeout(tick, 400)
        }
      }, timings[step] * 1000)
    }

    const id = setTimeout(tick, 300)
    return () => clearTimeout(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, isPaused])

  /* Auto-scroll log */
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  const doneCount    = steps.filter(s => s.status === 'done').length
  const currentStepObj = steps.find(s => s.status === 'running')

  return (
    <PageShell
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(145deg, #050a1a 0%, #0a0f2e 50%, #140a2e 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Ambient orbs */}
      <motion.div
        style={{ position: 'absolute', top: '5%', left: '5%', width: '600px', height: '600px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)', pointerEvents: 'none' }}
        animate={{ x: [0, 18, -12, 0], y: [0, -28, 16, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        style={{ position: 'absolute', bottom: '5%', right: '5%', width: '500px', height: '500px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(139,92,246,0.1) 0%, transparent 70%)', pointerEvents: 'none' }}
        animate={{ x: [0, -20, 10, 0], y: [0, 22, -18, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Header */}
      <div style={{ position: 'absolute', top: '1.5rem', left: '2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div style={{ width: '28px', height: '28px', borderRadius: '7px', background: 'var(--gradient-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span className="material-icons-round" style={{ color: 'white', fontSize: '0.9rem' }}>auto_fix_high</span>
        </div>
        <span style={{ fontFamily: 'Sora, sans-serif', fontWeight: 700, fontSize: '1rem', color: 'white', letterSpacing: '-0.02em' }}>Syncademic</span>
      </div>

      <div style={{ width: '100%', maxWidth: '680px', position: 'relative', zIndex: 1 }}>

        {/* Title */}
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <div className="chip chip-blue" style={{ display: 'inline-flex', marginBottom: '1rem', background: 'rgba(59,130,246,0.15)', color: '#93c5fd' }}>
            <span className="material-icons-round" style={{ fontSize: '0.85rem' }}>auto_fix_high</span>
            Algorithmic Engine
          </div>
          <h1
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: 'clamp(1.75rem, 3vw, 2.5rem)',
              fontWeight: 800,
              color: 'white',
              letterSpacing: '-0.03em',
              marginBottom: '0.5rem',
            }}
          >
            Optimizing Academic Calendars
          </h1>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', color: 'rgba(255,255,255,0.5)' }}>
            {currentStepObj ? currentStepObj.label : isPaused ? 'Paused' : 'Initializing...'}
          </p>
        </div>

        {/* Progress bar */}
        <div
          style={{
            height: '6px',
            background: 'rgba(255,255,255,0.08)',
            borderRadius: '99px',
            overflow: 'hidden',
            marginBottom: '0.75rem',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progress}%`,
              background: 'var(--gradient-primary)',
              borderRadius: '99px',
              transition: 'width 0.5s ease',
              boxShadow: '0 0 12px rgba(59,130,246,0.6)',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', letterSpacing: '0.04em' }}>
            Processing... {progress}%
          </span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', letterSpacing: '0.04em' }}>
            {doneCount} / {steps.length} steps
          </span>
        </div>

        {/* Main glass card */}
        <div
          className="glass"
          style={{ borderRadius: '1.5rem', padding: '2rem', marginBottom: '1.25rem' }}
        >
          {/* Steps */}
          <div style={{ marginBottom: '1.5rem' }}>
            {steps.map((step, i) => (
              <StepRow key={step.label} step={step} index={i} isCurrent={step.status === 'running'} />
            ))}
          </div>

          {/* Engine load */}
          <div
            style={{
              borderTop: '1px solid rgba(255,255,255,0.08)',
              paddingTop: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
            }}
          >
            <div>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em', display: 'block', marginBottom: '0.25rem' }}>
                ENGINE LOAD
              </span>
              <div style={{ display: 'flex', gap: '3px' }}>
                {Array.from({ length: 10 }).map((_, i) => (
                  <div
                    key={i}
                    style={{
                      width: '6px',
                      height: '20px',
                      borderRadius: '2px',
                      background: i < Math.round(engineLoad / 10)
                        ? `hsl(${220 + i * 5}, 90%, ${65 - i * 2}%)`
                        : 'rgba(255,255,255,0.08)',
                      transition: 'background 0.3s',
                    }}
                  />
                ))}
              </div>
            </div>

            <div style={{ flex: 1 }} />

            <div style={{ textAlign: 'right' }}>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em', display: 'block', marginBottom: '0.25rem' }}>
                SOLVER STATUS
              </span>
              <span
                className="chip"
                style={{
                  background: isPaused ? 'rgba(245,158,11,0.2)' : 'rgba(16,185,129,0.15)',
                  color: isPaused ? '#fbbf24' : '#6ee7b7',
                }}
              >
                {isPaused ? 'PAUSED' : isRunning ? 'ACTIVE' : 'IDLE'}
              </span>
            </div>
          </div>
        </div>

        {/* Log output */}
        <div
          ref={logRef}
          className="glass"
          style={{
            borderRadius: '1rem',
            padding: '1rem',
            height: '120px',
            overflowY: 'auto',
            marginBottom: '1.5rem',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '0.72rem',
            color: 'rgba(255,255,255,0.45)',
            lineHeight: 1.7,
          }}
        >
          {logs.length === 0 ? (
            <span style={{ color: 'rgba(255,255,255,0.2)' }}>Awaiting engine output...</span>
          ) : (
            logs.map((line, i) => <div key={i}>{line}</div>)
          )}
        </div>

        {/* Controls */}
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
          <button
            className="btn-ghost"
            onClick={pauseProcessing}
            style={{ gap: '0.4rem' }}
          >
            <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>
              {isPaused ? 'play_circle' : 'pause_circle'}
            </span>
            {isPaused ? 'RESUME ENGINE' : 'PAUSE ENGINE'}
          </button>
          <button
            onClick={() => { cancelProcessing(); }}
            style={{
              background: 'rgba(186,26,26,0.15)',
              color: '#fca5a5',
              border: '1px solid rgba(186,26,26,0.25)',
              borderRadius: '9999px',
              padding: '0.75rem 2rem',
              fontFamily: 'Sora, sans-serif',
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            CANCEL
          </button>
        </div>
      </div>
    </PageShell>
  )
}
