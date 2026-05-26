import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon, Chip, WorkspaceShell, useCurrent } from './Shared'

const STEPS = [
  { label: 'Validating structural constraints',  time: '0.42s' },
  { label: 'Building O(n²) conflict graph',       time: '1.18s' },
  { label: 'Applying MCV heuristics',             time: '2.04s' },
  { label: 'Executing CSP backtracking engine',   time: '3.81s' },
  { label: 'Cross-checking arc consistency',      time: '1.46s' },
  { label: 'Streaming three solver variants',     time: '0.92s' },
]

function CountUp({ value }) {
  return <span className="font-mono">{value.toLocaleString()}</span>
}

function EngineSpark({ active }) {
  const [bars, setBars] = useState([45, 60, 30, 80, 55, 35, 70, 50, 90, 40, 65, 45])
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setBars(b => b.map(() => 25 + Math.random() * 75)), 220)
    return () => clearInterval(id)
  }, [active])
  return (
    <div className="flex items-end gap-1.5 h-24">
      {bars.map((h, i) => (
        <div key={i} className="flex-1 rounded-t-sm transition-all duration-200"
          style={{
            height: `${h}%`,
            background: `linear-gradient(180deg, #adc6ff 0%, rgba(139,92,246,${0.3 + (h / 100) * 0.4}) 100%)`,
            boxShadow: h > 70 ? '0 0 8px rgba(173,198,255,0.5)' : 'none',
          }}
        />
      ))}
    </div>
  )
}

function SolverLog({ progress }) {
  const lines = [
    { p: 5,  c: '#8c909f', t: '[init] worker pool spun up · 128 threads'             },
    { p: 12, c: '#adc6ff', t: '[graph] built conflict graph · 2,847 edges'            },
    { p: 22, c: '#adc6ff', t: '[mcv] selecting most constrained variable'             },
    { p: 38, c: '#d0bcff', t: '[csp] backtracking from depth 41 → 26'                },
    { p: 52, c: '#d0bcff', t: '[arc] consistency forward-pass complete'               },
    { p: 68, c: '#ffb786', t: "[stream] variant 'Optimal' converged @ 21 days"        },
    { p: 82, c: '#ffb786', t: "[stream] variant 'Fastest' converged @ 14 days"        },
    { p: 95, c: '#adc6ff', t: "[stream] variant 'Relaxed' converged @ 28 days"        },
    { p: 99, c: '#adc6ff', t: '[done] all three timelines published'                  },
  ]
  const visible = lines.filter(l => l.p <= progress)
  return (
    <div className="font-mono text-[11px] space-y-1.5 max-h-[180px] overflow-hidden">
      {visible.slice(-8).map((l, i) => (
        <div key={i} style={{ color: l.c, opacity: 0.5 + (i / visible.slice(-8).length) * 0.5 }}>{l.t}</div>
      ))}
      {progress < 100 && <div className="text-on-surface-variant/40">▌</div>}
    </div>
  )
}

export default function ProcessingState() {
  const navigate = useNavigate()
  const current = useCurrent()
  const [progress, setProgress] = useState(0)
  const [paused,   setPaused]   = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [done,     setDone]     = useState(false)

  useEffect(() => {
    if (paused || done) return
    const id = setInterval(() => {
      setProgress(p => {
        const next = p + 0.7 + Math.random() * 0.6
        if (next >= 100) { clearInterval(id); setDone(true); return 100 }
        return next
      })
    }, 80)
    return () => clearInterval(id)
  }, [paused, done])

  useEffect(() => {
    setActiveStep(Math.min(STEPS.length - 1, Math.floor((progress / 100) * STEPS.length)))
  }, [progress])

  useEffect(() => {
    if (done) {
      const t = setTimeout(() => navigate('/results'), 1400)
      return () => clearTimeout(t)
    }
  }, [done, navigate])

  return (
    <WorkspaceShell
      current={current}
      title="Algorithmic Engine"
      subtitle="Solver v4.2.0"
      right={
        <Chip tone={done ? 'primary' : 'secondary'} className="mr-2">
          <span className="w-1.5 h-1.5 rounded-full pulse-soft" style={{ background: done ? '#adc6ff' : '#d0bcff' }} />
          {done ? 'Finalized' : 'Processing'}
        </Chip>
      }
    >
      <div className="screen-anim grid grid-cols-12 gap-6">

        {/* Central card */}
        <div className="col-span-12 lg:col-span-8 glass rounded-[32px] p-8 md:p-10 relative overflow-hidden shimmer">
          <div className="absolute -top-32 -right-32 w-80 h-80 rounded-full pointer-events-none"
            style={{ background: 'rgba(139,92,246,0.18)', filter: 'blur(80px)' }} />

          <div className="flex flex-col items-center text-center mb-10 relative">
            <div className="relative mb-5">
              <div className="absolute inset-0 rounded-2xl blur-2xl"
                style={{ background: 'rgba(173,198,255,0.4)', animation: 'pulse-soft 2s ease-in-out infinite' }} />
              <div className="relative w-20 h-20 rounded-2xl p-0.5"
                style={{ background: 'linear-gradient(135deg, #adc6ff 0%, #d0bcff 100%)', boxShadow: '0 0 40px -10px rgba(173,198,255,0.7)' }}>
                <div className="w-full h-full rounded-[14px] flex items-center justify-center relative overflow-hidden"
                  style={{ background: '#0b1326' }}>
                  <Icon name="auto_fix_high" fill className="text-[34px] text-primary relative z-10" />
                  <div className="absolute inset-0 spin-slow" style={{
                    background: 'conic-gradient(from 0deg, rgba(173,198,255,0.2), transparent 60%, rgba(208,188,255,0.3), transparent)',
                  }} />
                </div>
              </div>
            </div>
            <h1 className="text-[28px] md:text-[32px] font-extrabold tracking-tight mb-2">Algorithmic engine</h1>
            <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold">Optimizing academic calendars</p>
          </div>

          <div className="mb-7">
            <div className="flex items-center justify-between text-[13px] mb-3">
              <span className="text-primary font-bold flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-primary pulse-soft" style={{ boxShadow: '0 0 8px #adc6ff' }} />
                Engine status: <span className="text-on-surface font-semibold ml-1">{done ? 'Solved' : paused ? 'Paused' : 'Solving…'}</span>
              </span>
              <span className="font-mono text-[14px] text-on-surface">{Math.floor(progress)}%</span>
            </div>
            <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden">
              <div className="h-full transition-[width] duration-300 ease-out relative"
                style={{
                  width: `${progress}%`,
                  background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                  boxShadow: '0 0 16px rgba(173,198,255,0.6)',
                }}>
                <div className="absolute inset-0 shimmer" />
              </div>
            </div>
          </div>

          <div className="space-y-3 mb-7">
            {STEPS.map((s, i) => {
              const status = i < activeStep ? 'done' : i === activeStep && !done ? 'live' : i === activeStep && done ? 'done' : 'wait'
              return (
                <div key={i} className="flex items-center justify-between p-4 rounded-xl transition-all duration-500"
                  style={
                    status === 'live'
                      ? { background: 'rgba(173,198,255,0.08)', border: '1px solid rgba(173,198,255,0.25)', boxShadow: '0 0 20px rgba(173,198,255,0.15)', transform: 'scale(1.01)' }
                      : status === 'done'
                      ? { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }
                      : { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', opacity: 0.45 }
                  }
                >
                  <div className="flex items-center gap-4">
                    {status === 'live'
                      ? <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                      : status === 'done'
                      ? <Icon name="check_circle" fill className="text-primary text-[20px]" />
                      : <Icon name="radio_button_unchecked" className="text-on-surface-variant/50 text-[20px]" />
                    }
                    <span className={`text-[14px] ${status === 'live' ? 'text-primary font-semibold' : 'text-on-surface'}`}>{s.label}</span>
                  </div>
                  <span className={`text-[11px] font-mono uppercase tracking-widest ${status === 'live' ? 'text-primary pulse-soft' : 'text-on-surface-variant/50'}`}>
                    {status === 'live' ? 'LIVE' : status === 'done' ? s.time : 'WAIT'}
                  </span>
                </div>
              )
            })}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setPaused(!paused)} disabled={done}
              className="btn-grad flex-1 py-4 rounded-xl font-semibold uppercase tracking-[0.08em] text-[12px] flex items-center justify-center gap-2">
              <Icon name={paused ? 'play_circle' : 'pause_circle'} className="text-[18px]" />
              {paused ? 'Resume engine' : 'Pause engine'}
            </button>
            <button onClick={() => navigate('/dashboard')}
              className="px-6 py-4 rounded-xl border border-white/10 text-on-surface-variant hover:bg-white/5 transition-all text-[12px] uppercase tracking-[0.08em] font-semibold">
              Cancel
            </button>
          </div>

          {done && (
            <div className="mt-6 glass-inner rounded-xl p-4 flex items-center justify-between screen-anim">
              <div className="flex items-center gap-3">
                <Icon name="check_circle" fill className="text-primary text-[22px]" />
                <span className="text-[14px] font-semibold">Three optimal schedules streamed. Redirecting…</span>
              </div>
              <button onClick={() => navigate('/results')} className="text-primary text-[12px] uppercase tracking-[0.08em] font-bold hover:underline flex items-center gap-1">
                View results <Icon name="arrow_forward" className="text-[14px]" />
              </button>
            </div>
          )}
        </div>

        {/* Side panels */}
        <div className="col-span-12 lg:col-span-4 space-y-6">
          <div className="glass rounded-3xl p-6">
            <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-4">Engine load</p>
            <EngineSpark active={!paused && !done} />
            <div className="grid grid-cols-2 gap-4 mt-5 pt-5 border-t border-white/5">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-on-surface-variant/50">CPU threads</div>
                <div className="text-[22px] font-bold text-primary">128</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-on-surface-variant/50">Memory</div>
                <div className="text-[22px] font-bold text-secondary">42 GB</div>
              </div>
            </div>
          </div>

          <div className="glass rounded-3xl p-6">
            <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-4">Conflicts resolved</p>
            <div className="flex items-end gap-2 mb-3">
              <div className="text-[44px] font-extrabold leading-none">
                <CountUp value={Math.floor(2847 * (progress / 100))} />
              </div>
              <div className="text-on-surface-variant/60 text-[12px] mb-1">of 2,847</div>
            </div>
            <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
              <div className="h-full transition-all" style={{ width: `${progress}%`, background: '#adc6ff' }} />
            </div>
            <div className="grid grid-cols-3 gap-3 mt-5">
              {[
                { l: 'Student', v: 1245, tone: 'primary'   },
                { l: 'Faculty', v: 612,  tone: 'secondary' },
                { l: 'Venue',   v: 990,  tone: 'tertiary'  },
              ].map(s => (
                <div key={s.l} className="glass-inner rounded-lg p-3">
                  <div className={`text-[16px] font-bold ${s.tone === 'primary' ? 'text-primary' : s.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`}>
                    <CountUp value={Math.floor(s.v * (progress / 100))} />
                  </div>
                  <div className="text-[10px] uppercase tracking-widest text-on-surface-variant/50 mt-1">{s.l}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass rounded-3xl p-6">
            <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-4">Solver log</p>
            <SolverLog progress={progress} />
          </div>
        </div>
      </div>
    </WorkspaceShell>
  )
}
