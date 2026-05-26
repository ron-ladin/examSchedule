import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon, Chip, GradButton, GhostButton, WorkspaceShell, useCurrent } from './Shared'

const CARDS = {
  optimal: {
    glow: { bg: 'rgba(173,198,255,0.20)', outer: 'rgba(173,198,255,0.18)', border: 'rgba(173,198,255,0.35)', fg: '#adc6ff' },
    badge: 'Best balance', badgeTone: 'primary', n: 1, name: 'Optimal', icon: 'star',
    duration: '21 days', durationColor: '#dae2fd', studyGap: '3.2 days', gapBar: 85, load: 'Moderate',
  },
  fastest: {
    glow: { bg: 'rgba(208,188,255,0.20)', outer: 'rgba(208,188,255,0.18)', border: 'rgba(208,188,255,0.35)', fg: '#d0bcff' },
    badge: 'Time efficient', badgeTone: 'secondary', n: 2, name: 'Fastest', icon: 'bolt',
    duration: '14 days', durationColor: '#d0bcff', studyGap: '1.8 days', gapBar: 95, load: 'Intense',
  },
  relaxed: {
    glow: { bg: 'rgba(255,183,134,0.20)', outer: 'rgba(255,183,134,0.18)', border: 'rgba(255,183,134,0.35)', fg: '#ffb786' },
    badge: 'Low pressure', badgeTone: 'tertiary', n: 3, name: 'Relaxed', icon: 'self_improvement',
    duration: '28 days', durationColor: '#ffb786', studyGap: '4.5 days', gapBar: 60, load: 'Minimal',
  },
}

function ResultCard({ c, selected, onSelect }) {
  const { glow, badge, badgeTone, n, name, icon, duration, durationColor, studyGap, gapBar, load } = c
  return (
    <div
      onClick={onSelect}
      className="glass glass-hover rounded-[28px] p-7 flex flex-col relative overflow-hidden cursor-pointer transition-all"
      style={selected ? {
        borderColor: glow.border,
        boxShadow: `0 0 60px ${glow.outer}, 0 30px 60px -12px rgba(0,0,0,0.55)`,
        transform: 'translateY(-4px)',
      } : {}}
    >
      <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full pointer-events-none transition-all duration-500"
        style={{ background: glow.bg, filter: 'blur(60px)' }} />

      <div className="relative flex justify-between items-start mb-7">
        <div className="flex flex-col gap-2">
          <Chip tone={badgeTone}>{badge}</Chip>
          <h3 className="text-[24px] font-bold leading-tight">
            Option {n}<br /><span className="grad-text-cool">{name}</span>
          </h3>
        </div>
        <div className="w-12 h-12 rounded-2xl glass-inner flex items-center justify-center"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)' }}>
          <Icon name={icon} fill className="text-[26px]" style={{ color: glow.fg }} />
        </div>
      </div>

      <div className="relative grid grid-cols-2 gap-3 mb-7">
        <div className="glass-inner rounded-2xl p-4">
          <p className="text-[10px] uppercase tracking-widest text-on-surface-variant/60 mb-1">Conflicts</p>
          <p className="text-[28px] font-bold text-primary leading-none">0</p>
        </div>
        <div className="glass-inner rounded-2xl p-4">
          <p className="text-[10px] uppercase tracking-widest text-on-surface-variant/60 mb-1">Duration</p>
          <p className="text-[28px] font-bold leading-none" style={{ color: durationColor }}>{duration}</p>
        </div>
      </div>

      <div className="relative flex flex-col gap-3 mb-7">
        <div className="flex justify-between items-center">
          <span className="text-[13px] text-on-surface-variant">Avg. study gap</span>
          <span className="text-[12px] uppercase tracking-widest text-on-surface font-semibold">{studyGap}</span>
        </div>
        <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700"
            style={{ width: `${gapBar}%`, background: glow.fg, boxShadow: `0 0 12px ${glow.fg}88` }} />
        </div>
        <div className="flex justify-between items-center">
          <span className="text-[13px] text-on-surface-variant">Resource load</span>
          <span className="text-[12px] uppercase tracking-widest font-semibold" style={{ color: glow.fg }}>{load}</span>
        </div>
      </div>

      <button className="relative mt-auto flex items-center justify-center gap-2 py-3.5 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/[0.08] transition-all text-[12px] uppercase tracking-[0.08em] font-semibold text-on-surface group/link">
        Explore details
        <Icon name="arrow_forward" className="text-[14px] group-hover/link:translate-x-1 transition-transform" />
      </button>

      {selected && (
        <div className="absolute top-4 right-4 rounded-full p-1.5" style={{ background: glow.fg, boxShadow: `0 0 16px ${glow.fg}` }}>
          <Icon name="check" className="text-[14px] text-on-primary" />
        </div>
      )}
    </div>
  )
}

function DistroChart({ selected }) {
  const distros = {
    optimal: [40, 70, 90, 50, 20],
    fastest: [85, 95, 100, 0, 0],
    relaxed: [30, 50, 60, 55, 45],
  }
  const colors = {
    optimal: { mid: 'rgba(173,198,255,0.55)', low: 'rgba(173,198,255,0.18)' },
    fastest: { mid: 'rgba(208,188,255,0.55)', low: 'rgba(208,188,255,0.18)' },
    relaxed: { mid: 'rgba(255,183,134,0.55)', low: 'rgba(255,183,134,0.18)' },
  }
  const data = distros[selected], c = colors[selected], max = Math.max(...data, 1)
  return (
    <div>
      <div className="flex items-end gap-3 h-48">
        {data.map((v, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-2 group">
            <div className="text-[11px] text-on-surface-variant/60 font-mono opacity-0 group-hover:opacity-100 transition-opacity">{v}%</div>
            <div className="w-full rounded-t-xl transition-all duration-700"
              style={{
                height: `${(v / max) * 100}%`,
                background: v > 70 ? c.mid : c.low,
                boxShadow: v > 70 ? `0 0 18px ${c.mid}` : 'none',
              }} />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-4 text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/50 font-semibold">
        {['Week 1','Week 2','Week 3','Week 4','Week 5'].map(w => <span key={w}>{w}</span>)}
      </div>
    </div>
  )
}

export default function ResultsView() {
  const navigate = useNavigate()
  const current = useCurrent()
  const [selected, setSelected] = useState('optimal')
  const [moed, setMoed] = useState('A')

  const sel = CARDS[selected]

  return (
    <WorkspaceShell
      current={current}
      title="Results"
      subtitle="Winter 2026"
      right={
        <Chip tone="primary" className="mr-2">
          <Icon name="check_circle" fill className="text-[12px]" /> 3 timelines streamed
        </Chip>
      }
    >
      <div className="screen-anim space-y-10">

        {/* Filter bar */}
        <section className="glass rounded-2xl p-5 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-5">
          <div className="flex flex-wrap gap-5 items-center">
            <div className="flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">Semester</span>
              <select className="liquid-input rounded-lg px-4 py-2 text-[13px] min-w-[180px]">
                <option>Winter 2026</option>
                <option>Spring 2026</option>
                <option>Fall 2025</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">Examination period</span>
              <div className="flex glass-inner p-1 rounded-lg">
                {['A', 'B', 'Resit'].map(m => (
                  <button key={m} onClick={() => setMoed(m)}
                    className="px-4 py-1.5 rounded-md text-[12px] uppercase tracking-[0.08em] font-semibold transition-all"
                    style={moed === m ? {
                      background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                      color: '#fff',
                      boxShadow: '0 0 14px rgba(173,198,255,0.4)',
                    } : { color: 'rgba(218,226,253,0.6)' }}>
                    Moed {m}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <GhostButton size="sm" icon="tune">Advanced filters</GhostButton>
            <GradButton size="sm" icon="refresh" onClick={() => navigate('/processing')}>Re-calculate</GradButton>
          </div>
        </section>

        {/* Schedule cards */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {Object.entries(CARDS).map(([key, c]) => (
            <ResultCard key={key} c={c} selected={selected === key} onSelect={() => setSelected(key)} />
          ))}
        </section>

        {/* Analytics */}
        <section className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7 glass rounded-3xl p-7">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-2">Distribution by week</p>
                <h3 className="text-[22px] font-semibold">Exam load · Option {sel.n} ({sel.name})</h3>
              </div>
              <Chip tone={sel.badgeTone}>{sel.badge}</Chip>
            </div>
            <DistroChart selected={selected} />
            <div className="grid grid-cols-4 gap-4 mt-6 pt-6 border-t border-white/5">
              {[
                { k: 'Peak day',        v: 'Dec 13' },
                { k: 'Empty slots',     v: '46'     },
                { k: 'Cross-faculty',   v: '12%'    },
                { k: 'Avg students',    v: '58'     },
              ].map(m => (
                <div key={m.k}>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold mb-1">{m.k}</div>
                  <div className="text-[20px] font-bold text-on-surface">{m.v}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5 flex flex-col gap-6">
            <div className="glass rounded-3xl p-7 flex-1 flex flex-col items-center text-center justify-center">
              <div className="relative w-32 h-32 mb-5">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="url(#health-grad)" strokeWidth="2"
                    strokeDasharray="99.8 100" strokeLinecap="round"
                    style={{ filter: 'drop-shadow(0 0 6px rgba(173,198,255,0.5))' }} />
                  <defs>
                    <linearGradient id="health-grad" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <Icon name="auto_awesome" fill className="text-primary text-[20px] mb-1" />
                  <div className="text-[20px] font-bold">99.8%</div>
                </div>
              </div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">Solver health</p>
            </div>

            <div className="glass rounded-3xl p-6 flex flex-col justify-between">
              <div>
                <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-3">Upcoming deadline</p>
                <p className="text-[14px] text-on-surface leading-relaxed">Submit Moed A schedule to the registrar.</p>
              </div>
              <div className="flex items-center gap-2 mt-5 text-tertiary">
                <Icon name="alarm" className="text-[16px]" />
                <span className="text-[12px] uppercase tracking-widest font-bold">2 days left</span>
              </div>
            </div>
          </div>
        </section>

        {/* Comparison table */}
        <section className="glass rounded-3xl p-7">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-[22px] font-semibold">Side-by-side comparison</h3>
            <GradButton size="sm" icon="check" onClick={() => navigate('/calendar')}>Deploy {sel.name}</GradButton>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 border-b border-white/5">
                  <th className="py-3 pr-4">Metric</th>
                  {Object.values(CARDS).map(c => (
                    <th key={c.name} className="py-3 px-4" style={{ color: c.glow.fg }}>{c.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { k: 'Duration',              v: ['21 days', '14 days', '28 days'] },
                  { k: 'Conflicts',             v: ['0', '0', '0'] },
                  { k: 'Avg. study gap',        v: ['3.2 days', '1.8 days', '4.5 days'] },
                  { k: 'Peak student load/day', v: ['112', '168', '82'] },
                  { k: 'Room utilization',      v: ['86%', '94%', '61%'] },
                  { k: 'Faculty travel time',   v: ['Low', 'Moderate', 'Minimal'] },
                  { k: 'Weekend exams',         v: ['1', '3', '0'] },
                ].map((row, i) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="py-3 pr-4 text-on-surface-variant/80">{row.k}</td>
                    {row.v.map((v, j) => (
                      <td key={j} className={`py-3 px-4 font-semibold ${j === 0 ? 'text-on-surface' : 'text-on-surface-variant'}`}>{v}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </WorkspaceShell>
  )
}
