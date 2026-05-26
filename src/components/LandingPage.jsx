import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon, AmbientOrbs, BrandMark, Chip, GradButton, GhostButton } from './Shared'

function LandingNav() {
  const navigate = useNavigate()
  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 flex justify-between items-center px-6 md:px-16 py-5"
      style={{
        background: 'rgba(11,19,38,0.55)',
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}
    >
      <button onClick={() => navigate('/')} className="text-left">
        <BrandMark size={38} />
      </button>
      <nav className="hidden md:flex gap-10 text-[12px] uppercase tracking-[0.16em] font-semibold">
        <a className="text-primary border-b-2 border-primary pb-1" href="#features">Platform</a>
        <a className="text-on-surface-variant hover:text-primary transition-colors" href="#how">How it works</a>
        <a className="text-on-surface-variant hover:text-primary transition-colors" href="#faq">Resources</a>
        <a className="text-on-surface-variant hover:text-primary transition-colors" href="#cta">Pricing</a>
      </nav>
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/login')}
          className="text-on-surface hover:text-primary transition-colors text-[12px] uppercase tracking-[0.08em] font-semibold px-4 py-2"
        >
          Sign In
        </button>
        <button
          onClick={() => navigate('/register')}
          className="btn-ghost glass px-5 py-2.5 rounded-full text-[12px] uppercase tracking-[0.08em] font-semibold text-on-surface"
        >
          Join Waitlist
        </button>
      </div>
    </header>
  )
}

function HeroMockup() {
  const cells = useMemo(() => ({
    '0-1': { code: 'CS-401',   tone: 'primary'   },
    '1-0': { code: 'MATH-101', tone: 'secondary' },
    '2-2': { code: 'PHYS-202', tone: 'tertiary'  },
    '2-3': { code: 'ECON-101', tone: 'error', conflict: true },
    '3-1': { code: 'LIT-330',  tone: 'secondary' },
    '4-0': { code: 'CS-205',   tone: 'primary'   },
    '4-2': { code: 'CHEM-201', tone: 'primary'   },
  }), [])

  const toneStyle = (tone) => ({
    primary:   { bg: 'rgba(173,198,255,0.14)', bd: '#adc6ff', fg: '#adc6ff' },
    secondary: { bg: 'rgba(208,188,255,0.14)', bd: '#d0bcff', fg: '#d0bcff' },
    tertiary:  { bg: 'rgba(255,183,134,0.14)', bd: '#ffb786', fg: '#ffb786' },
    error:     { bg: 'rgba(147,0,10,0.30)',    bd: '#ff8a82', fg: '#ffb4ab' },
  })[tone]

  const days = ['MON', 'TUE', 'WED', 'THU', 'FRI']

  return (
    <div className="relative">
      <div className="absolute -inset-12 rounded-[60px] opacity-60 pointer-events-none" style={{
        background: 'radial-gradient(60% 60% at 50% 20%, rgba(59,130,246,0.30), transparent 70%), radial-gradient(60% 60% at 50% 80%, rgba(139,92,246,0.25), transparent 70%)',
        filter: 'blur(40px)',
      }} />
      <div className="glass rounded-[28px] p-5 md:p-7 relative overflow-hidden">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#ff8a82' }} />
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#ffb786' }} />
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#adc6ff' }} />
            </div>
            <span className="ml-3 text-[10px] uppercase tracking-[0.2em] text-on-surface-variant/60 font-semibold">
              app.syncademic.io / schedules / winter-2026
            </span>
          </div>
          <Chip tone="primary">Live</Chip>
        </div>

        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-3 hidden md:flex flex-col gap-2">
            <div className="glass-inner rounded-xl p-3">
              <p className="text-[9px] uppercase tracking-widest text-on-surface-variant/60 mb-2">Engine</p>
              <p className="text-[12px] font-semibold text-primary mb-2">Optimal v4.2</p>
              <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                <div className="h-full" style={{ width: '84%', background: 'linear-gradient(90deg,#3b82f6,#8b5cf6)' }} />
              </div>
              <p className="text-[10px] text-on-surface-variant/60 mt-2">0 conflicts · 142 exams</p>
            </div>
          </div>

          <div className="col-span-12 md:col-span-9">
            <div className="grid grid-cols-5 gap-2 mb-2">
              {days.map(d => (
                <div key={d} className="text-[10px] uppercase tracking-[0.18em] font-bold text-on-surface-variant/60 text-center py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-5 gap-2">
              {Array.from({ length: 25 }).map((_, idx) => {
                const r = Math.floor(idx / 5), c = idx % 5
                const ev = cells[`${r}-${c}`]
                const isToday = r === 1 && c === 2
                return (
                  <div key={idx} className="glass-inner rounded-lg h-[58px] p-2 relative"
                    style={isToday ? { boxShadow: 'inset 0 0 0 1px rgba(173,198,255,0.5), 0 0 18px rgba(173,198,255,0.2)' } : {}}>
                    <span className={`text-[9px] font-semibold ${isToday ? 'text-primary' : 'text-on-surface-variant/70'}`}>
                      {(idx + 4).toString().padStart(2, '0')}
                    </span>
                    {ev && (() => {
                      const s = toneStyle(ev.tone)
                      return (
                        <div className="absolute left-1.5 right-1.5 bottom-1.5 px-1.5 py-1 rounded text-[8.5px] font-bold tracking-wide truncate"
                          style={{ background: s.bg, color: s.fg, borderLeft: `2px solid ${s.bd}` }}>
                          {ev.conflict && '⚠ '}{ev.code}
                        </div>
                      )
                    })()}
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-3">
          {[
            { k: 'Conflicts',     v: '0',     tone: 'primary'   },
            { k: 'Avg gap',       v: '3.2d',  tone: 'secondary' },
            { k: 'Solver health', v: '99.8%', tone: 'tertiary'  },
          ].map(m => (
            <div key={m.k} className="glass-inner rounded-xl p-3 flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-widest text-on-surface-variant/60">{m.k}</span>
              <span className={`text-[16px] font-bold ${m.tone === 'primary' ? 'text-primary' : m.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`}>{m.v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function FAQRow({ q, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <button onClick={() => setOpen(!open)} className="glass rounded-2xl p-5 w-full text-left transition-all glass-hover">
      <div className="flex justify-between items-center gap-4">
        <span className="font-semibold text-[14px] text-on-surface">{q}</span>
        <Icon name="expand_more" className={`text-primary transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </div>
      <div className="grid transition-all duration-300 ease-out overflow-hidden"
        style={{ gridTemplateRows: open ? '1fr' : '0fr', marginTop: open ? 12 : 0 }}>
        <div className="overflow-hidden">
          <p className="text-[13px] text-on-surface-variant/75 leading-relaxed">
            Yes — Syncademic exposes a REST API and pre-built connectors for Canvas, Moodle, and Blackboard. Once configured, schedules sync bidirectionally within seconds of any solver change.
          </p>
        </div>
      </div>
    </button>
  )
}

export default function LandingPage() {
  const navigate = useNavigate()

  const stats = [
    { v: '0',     k: 'Conflicts after run', tone: 'primary'   },
    { v: '12s',   k: 'Median solve time',   tone: 'secondary' },
    { v: '50k+',  k: 'Students supported',  tone: 'tertiary'  },
    { v: '99.8%', k: 'Solver health',       tone: 'primary'   },
  ]

  return (
    <div className="relative min-h-screen">
      <AmbientOrbs variant="default" />
      <div className="relative z-10 pt-20">
        <LandingNav />

        <section className="relative px-6 md:px-16 pt-16 md:pt-24 pb-20 max-w-[1280px] mx-auto screen-anim">
          <div className="flex justify-center mb-6">
            <Chip tone="primary"><Icon name="bolt" className="text-[12px]" /> v4.2 — Lazy Streaming Engine</Chip>
          </div>
          <h1 className="text-balance text-center font-extrabold tracking-tight leading-[1.05] text-[44px] md:text-[76px] mb-7 max-w-4xl mx-auto">
            Conflict-free academic<br />schedules. <span className="grad-text">Optimized instantly.</span>
          </h1>
          <p className="text-pretty text-center text-[17px] md:text-[19px] text-on-surface-variant/75 max-w-2xl mx-auto mb-10 leading-relaxed">
            Syncademic resolves the most complex exam, classroom, and faculty conflicts with constraint-satisfaction algorithms tuned for institutional scale.
          </p>
          <div className="flex flex-col md:flex-row gap-4 justify-center items-center mb-20">
            <GradButton size="lg" iconAfter="arrow_forward" onClick={() => navigate('/register')}>Start free trial</GradButton>
            <GhostButton size="lg" icon="play_arrow" onClick={() => navigate('/dashboard')}>See the engine</GhostButton>
          </div>

          <HeroMockup />

          <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-4">
            {stats.map(s => (
              <div key={s.k} className="glass rounded-2xl p-5 text-center glass-hover">
                <div className={`text-[32px] font-bold mb-1 ${s.tone === 'primary' ? 'text-primary' : s.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`}>{s.v}</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">{s.k}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="px-6 md:px-16 pb-20">
          <div className="max-w-[1280px] mx-auto border-t border-b border-white/5 py-10">
            <p className="text-center text-[10px] uppercase tracking-[0.3em] text-on-surface-variant/40 font-semibold mb-8">
              Trusted by registrars at research institutions worldwide
            </p>
            <div className="flex flex-wrap justify-center items-center gap-x-14 gap-y-6 opacity-50">
              {['NORTHFIELD U', 'BLACKWOOD COLLEGE', 'STERLING INSTITUTE', 'ATLAS POLYTECHNIC', 'MERIDIAN ACADEMY', 'VIRTECH UNIVERSITY'].map(s => (
                <div key={s} className="font-bold text-[14px] tracking-[0.18em] text-on-surface-variant">{s}</div>
              ))}
            </div>
          </div>
        </section>

        <section id="features" className="px-6 md:px-16 pb-24 max-w-[1280px] mx-auto">
          <div className="mb-12 text-center">
            <Chip tone="secondary" className="mb-4">The platform</Chip>
            <h2 className="text-balance text-[36px] md:text-[48px] font-bold leading-tight max-w-2xl mx-auto">
              A <span className="grad-text-cool">command center</span> for institutional time.
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
            <div className="md:col-span-8 glass glass-hover rounded-3xl p-10 relative overflow-hidden min-h-[300px] flex flex-col justify-between">
              <div className="absolute -top-32 -right-32 w-80 h-80 rounded-full" style={{ background: 'rgba(59,130,246,0.18)', filter: 'blur(80px)' }} />
              <div className="relative">
                <Icon name="dynamic_form" className="text-primary text-[40px] mb-6" />
                <h3 className="text-[26px] font-semibold mb-3">Algorithmic resolution at scale</h3>
                <p className="text-on-surface-variant/75 max-w-md leading-relaxed">
                  Proprietary backtracking combined with Most Constrained Variable heuristics. Zero overlaps even for cohorts above 50,000 students across 12 faculties.
                </p>
              </div>
              <div className="flex gap-2 mt-6 relative flex-wrap">
                <Chip tone="primary">Backtracking</Chip>
                <Chip tone="secondary">MCV heuristics</Chip>
                <Chip tone="tertiary">Arc consistency</Chip>
              </div>
            </div>

            <div className="md:col-span-4 glass glass-hover rounded-3xl p-10 relative overflow-hidden flex flex-col justify-center text-center min-h-[300px]">
              <Icon name="stream" className="text-secondary text-[40px] mb-5 mx-auto" />
              <h3 className="text-[22px] font-semibold mb-3">Lazy streaming engine</h3>
              <p className="text-on-surface-variant/75 text-[14px] leading-relaxed">
                Preview alternative timelines in real time without recompiling. Compare three solver strategies side-by-side.
              </p>
            </div>

            <div className="md:col-span-4 glass glass-hover rounded-3xl p-10 relative overflow-hidden min-h-[260px] flex flex-col">
              <Icon name="calendar_month" className="text-tertiary text-[40px] mb-5" />
              <h3 className="text-[22px] font-semibold mb-3">Holiday-aware</h3>
              <p className="text-on-surface-variant/75 text-[14px] leading-relaxed">
                Regional holiday calendars, religious observances, and maintenance windows handled as hard constraints.
              </p>
            </div>

            <div className="md:col-span-8 glass glass-hover rounded-3xl p-10 relative overflow-hidden" id="how">
              <h3 className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 mb-8 font-semibold">How it works</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {[
                  { n: '01', t: 'Ingest',    d: 'Drop student registrations, course inventory, and venue capacity. CSV, XLSX, or live API.', tone: 'primary' },
                  { n: '02', t: 'Constrain', d: 'Lock holidays, faculty availability, and accessibility needs as solver constraints.',         tone: 'secondary' },
                  { n: '03', t: 'Deploy',    d: 'Three optimal timelines — Optimal, Fastest, Relaxed — pushed to every institutional portal.', tone: 'tertiary' },
                ].map(s => (
                  <div key={s.n}>
                    <div className={`text-[40px] font-black opacity-30 mb-1 ${s.tone === 'primary' ? 'text-primary' : s.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`}>{s.n}</div>
                    <h4 className="font-bold mb-2 text-[15px]">{s.t}</h4>
                    <p className="text-[12.5px] text-on-surface-variant/70 leading-relaxed">{s.d}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="cta" className="px-6 md:px-16 py-24 relative overflow-hidden" style={{ background: 'linear-gradient(180deg, transparent, rgba(6,14,32,0.6))' }}>
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.10), transparent)' }} />
          <div className="max-w-[1280px] mx-auto flex flex-col items-center text-center">
            <h2 className="text-balance text-[40px] md:text-[56px] font-bold leading-tight max-w-3xl mb-8">
              Ready to eliminate scheduling conflicts <span className="grad-text">forever</span>?
            </h2>
            <GradButton size="lg" iconAfter="bolt" onClick={() => navigate('/register')} className="mb-20">
              Optimize your institution
            </GradButton>

            <div id="faq" className="w-full max-w-3xl text-left border-t border-white/5 pt-16">
              <h4 className="text-center text-[10px] uppercase tracking-[0.3em] text-on-surface-variant/50 mb-10 font-semibold">Common inquiries</h4>
              <div className="space-y-3">
                {[
                  'Can Syncademic integrate with existing LMS platforms?',
                  'How does the algorithm handle last-minute room changes?',
                  'What is the processing time for a 10,000-student schedule?',
                  'Do you support custom religious or regional observance calendars?',
                ].map((q, i) => <FAQRow key={i} q={q} defaultOpen={i === 0} />)}
              </div>
            </div>
          </div>
        </section>

        <footer className="px-6 md:px-16 py-12 flex flex-col md:flex-row justify-between items-center gap-6 border-t border-white/5">
          <BrandMark size={36} />
          <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/50">© 2026 Syncademic Labs · Organic Noir Excellence</p>
          <div className="flex gap-7 text-[11px] uppercase tracking-[0.12em] text-on-surface-variant/60">
            {['Privacy', 'Terms', 'API', 'Support'].map(l => (
              <a key={l} className="hover:text-secondary" href="#">{l}</a>
            ))}
          </div>
        </footer>
      </div>
    </div>
  )
}
