import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon, GradButton, WorkspaceShell, useCurrent } from './Shared'

const EXAMS = {
  2:  [{ code: 'CS-401',   title: 'Algorithms',      tone: 'primary'   }, { code: 'MATH-101', title: 'Calculus I',       tone: 'secondary' }],
  3:  [{ code: 'PHYS-202', title: 'Magnetism',        tone: 'tertiary'  }],
  5:  [{ code: 'ECON-101', title: 'Macro',            tone: 'primary'   }],
  6:  [{ code: 'CS-205',   title: 'Operating Systems',tone: 'primary'   }, { code: 'CS-101', title: 'Intro CS', tone: 'primary' }],
  9:  [{ code: 'BIO-150',  title: 'Genetics',         tone: 'secondary' }],
  10: [{ code: 'CS-401',   title: 'Final',            tone: 'primary',  pulse: true }],
  11: [{ code: 'HIST-220', title: 'Mod. Hist.',       tone: 'tertiary'  }],
  12: [{ code: 'LIT-330',  title: 'Joyce',            tone: 'secondary' }, { code: 'PSYC-180', title: 'Cognition', tone: 'primary' }],
  13: [{ code: 'CHEM-201 ⨯ MATH-220', title: 'Conflict', tone: 'error', conflict: true }],
  16: [{ code: 'MATH-201', title: 'Linear Alg.',      tone: 'primary'   }],
  17: [{ code: 'ENG-310',  title: 'Romantics',        tone: 'secondary' }],
  18: [{ code: 'MATH-101', title: 'Calc I',           tone: 'primary'   }, { code: 'STAT-110', title: 'Stats',     tone: 'primary' }],
  19: [{ code: 'PHYS-101 ⨯ CS-303', title: 'Conflict', tone: 'error',   conflict: true }],
  20: [{ code: 'ARCH-440', title: 'Design Lab',       tone: 'tertiary'  }],
}

const toneStyles = {
  primary:   { bg: 'rgba(173,198,255,0.14)', bd: '#adc6ff', fg: '#adc6ff' },
  secondary: { bg: 'rgba(208,188,255,0.14)', bd: '#d0bcff', fg: '#d0bcff' },
  tertiary:  { bg: 'rgba(255,183,134,0.14)', bd: '#ffb786', fg: '#ffb786' },
  error:     { bg: 'rgba(147,0,10,0.35)',    bd: '#ff8a82', fg: '#ffb4ab' },
}

function LegendDot({ color, label, pulse }) {
  return (
    <div className="inline-flex items-center gap-2 glass-inner rounded-full px-3 py-1.5">
      <span className={`w-2 h-2 rounded-full ${pulse ? 'pulse-soft' : ''}`} style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      <span className="text-on-surface-variant/80 font-semibold text-[11px]">{label}</span>
    </div>
  )
}

function FocusedDayCard({ day }) {
  const exams = EXAMS[day] || []
  return (
    <div className="glass rounded-3xl p-6">
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold">Focused day</p>
        <Icon name="event" className="text-primary text-[18px]" />
      </div>
      <h3 className="text-[28px] font-bold mb-1">Dec {String(day).padStart(2, '0')}, 2026</h3>
      <p className="text-[11px] text-on-surface-variant/60 mb-5">
        {exams.length === 0 ? 'No exams scheduled' : `${exams.length} exam${exams.length === 1 ? '' : 's'} scheduled`}
      </p>

      {exams.length === 0 ? (
        <div className="glass-inner rounded-xl p-5 text-center text-[12px] text-on-surface-variant/60">
          <Icon name="event_available" className="text-on-surface-variant/40 text-[28px] mb-2 block" />
          Empty slot. Click <Icon name="add" className="text-[12px] align-middle" /> to schedule.
        </div>
      ) : (
        <div className="space-y-2.5">
          {exams.map((ev, i) => {
            const s = toneStyles[ev.tone]
            return (
              <div key={i} className="glass-inner rounded-xl p-3"
                style={{ borderLeft: `3px solid ${s.bd}`, boxShadow: ev.conflict ? 'inset 0 0 18px rgba(147,0,10,0.3)' : 'none' }}>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-bold" style={{ color: s.fg }}>{ev.conflict && '⚠ '}{ev.code}</span>
                  <span className="text-[10px] font-mono text-on-surface-variant/50">09:00 AM</span>
                </div>
                <p className="text-[11px] text-on-surface-variant/70 mt-1">{ev.title}</p>
                <div className="flex items-center gap-3 mt-2 text-[10px] text-on-surface-variant/50">
                  <span className="flex items-center gap-1"><Icon name="groups" className="text-[12px]" /> 142</span>
                  <span className="flex items-center gap-1"><Icon name="room" className="text-[12px]" /> Hall Alpha</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function InsightsCard() {
  return (
    <div className="glass rounded-3xl p-6">
      <div className="flex items-center gap-3 mb-5">
        <Icon name="insights" className="text-primary" />
        <h3 className="font-semibold text-[15px]">Schedule insights</h3>
      </div>
      <div className="space-y-4">
        <div className="glass-inner rounded-xl p-4 flex justify-between items-center">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-on-surface-variant/50 font-semibold">Total exams</p>
            <p className="text-[22px] font-bold text-primary">142</p>
          </div>
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon name="assignment" className="text-primary text-[18px]" />
          </div>
        </div>
        <div className="glass-inner rounded-xl p-4">
          <div className="flex justify-between items-center mb-2">
            <p className="text-[10px] uppercase tracking-widest text-on-surface-variant/50 font-semibold">Student overlaps</p>
            <span className="text-error text-[11px] font-bold">↑ 12%</span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div className="h-full bg-error rounded-full" style={{ width: '24%' }} />
          </div>
          <p className="mt-2 text-[10px] text-on-surface-variant/60">34 critical conflicts remaining</p>
        </div>
        <div className="glass-inner rounded-xl p-4">
          <div className="flex justify-between items-center mb-2">
            <p className="text-[10px] uppercase tracking-widest text-on-surface-variant/50 font-semibold">Room utilization</p>
            <span className="text-primary text-[11px] font-bold">88%</span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: '88%', background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)' }} />
          </div>
          <p className="mt-2 text-[10px] text-on-surface-variant/60">Peak: Dec 12 – Dec 15</p>
        </div>
      </div>
    </div>
  )
}

function PendingResolutionsCard() {
  const conflicts = [
    { t: 'CS-401 vs MATH-101',       s: 'Dec 10, 09:00 AM · 12 students',    level: 'error'    },
    { t: 'Room Alpha overcapacity',   s: 'Dec 12, 02:00 PM · PHYS-202',       level: 'tertiary' },
    { t: 'Prof. Miller double-booked',s: 'Dec 13 · 2 exams concurrent',       level: 'error'    },
    { t: 'Accessibility seat shortfall',s:'Dec 18 · STAT-110',                level: 'tertiary' },
  ]
  return (
    <div className="glass rounded-3xl p-6">
      <div className="flex justify-between items-center mb-5">
        <div className="flex items-center gap-3">
          <Icon name="warning" className="text-tertiary" />
          <h3 className="font-semibold text-[15px]">Pending resolutions</h3>
        </div>
        <span className="px-2 py-0.5 rounded-full bg-tertiary/10 text-tertiary text-[10px] font-bold">4 new</span>
      </div>
      <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
        {conflicts.map((c, i) => (
          <div key={i} className="glass-inner rounded-xl p-3 group hover:translate-x-1 transition-transform cursor-pointer"
            style={{ borderLeft: `3px solid ${c.level === 'error' ? '#ff8a82' : '#ffb786'}` }}>
            <p className="text-[12px] font-bold text-on-surface">{c.t}</p>
            <p className="text-[10px] text-on-surface-variant/60 mt-1">{c.s}</p>
            <div className="flex gap-3 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button className="text-[10px] font-bold text-primary hover:underline">Re-schedule</button>
              <button className="text-[10px] font-bold text-on-surface-variant hover:underline">Ignore</button>
            </div>
          </div>
        ))}
      </div>
      <button className="btn-grad w-full mt-5 py-3 rounded-xl text-[11px] uppercase tracking-[0.08em] font-bold flex items-center justify-center gap-2">
        <Icon name="auto_awesome" className="text-[14px]" /> Launch auto-resolver
      </button>
    </div>
  )
}

export default function DetailedCalendar() {
  const navigate = useNavigate()
  const current = useCurrent()
  const [focusedDay, setFocusedDay] = useState(10)

  // Dec 2026: Dec 1 is Tuesday. Prepend Nov 30 (Mon)
  const cells = []
  cells.push({ d: 30, prev: true })
  for (let i = 1; i <= 31; i++) cells.push({ d: i })
  for (let i = 1; i <= 4; i++) cells.push({ d: i, next: true })

  return (
    <WorkspaceShell
      current={current}
      title="December 2026"
      subtitle="Moed A · Week 50"
      right={
        <div className="flex items-center bg-white/5 rounded-full px-2 py-1 gap-1 border border-white/[0.08] mr-2">
          <button className="p-1.5 rounded-full hover:bg-white/5 text-on-surface-variant hover:text-primary">
            <Icon name="chevron_left" className="text-[18px]" />
          </button>
          <span className="px-3 text-[11px] uppercase tracking-[0.12em] font-semibold">Today</span>
          <button className="p-1.5 rounded-full hover:bg-white/5 text-on-surface-variant hover:text-primary">
            <Icon name="chevron_right" className="text-[18px]" />
          </button>
        </div>
      }
    >
      <div className="screen-anim grid grid-cols-12 gap-6">

        {/* Calendar grid */}
        <section className="col-span-12 lg:col-span-9">
          <div className="glass rounded-3xl overflow-hidden">
            <div className="grid grid-cols-7" style={{ background: 'rgba(6,14,32,0.5)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              {['MON','TUE','WED','THU','FRI','SAT','SUN'].map(d => (
                <div key={d} className="py-3.5 text-center text-[10px] uppercase tracking-[0.22em] font-semibold text-on-surface-variant/70">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 auto-rows-[120px]">
              {cells.map((cell, i) => {
                const muted = cell.prev || cell.next
                const exams = !muted ? EXAMS[cell.d] : null
                const isWeekend = (i % 7 === 5) || (i % 7 === 6)
                const isFocused = !muted && cell.d === focusedDay
                return (
                  <button key={i}
                    onClick={() => !muted && setFocusedDay(cell.d)}
                    className={`p-2.5 text-left relative transition-all duration-300 ${muted ? 'opacity-30 cursor-default' : 'hover:bg-white/[0.04]'}`}
                    style={{
                      background: isWeekend && !muted ? 'rgba(6,14,32,0.3)' : 'transparent',
                      borderRight: (i % 7) !== 6 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      boxShadow: isFocused ? 'inset 0 0 0 2px rgba(173,198,255,0.5), inset 0 0 30px rgba(173,198,255,0.12)' : 'none',
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`text-[11px] font-semibold ${isFocused ? 'text-primary' : 'text-on-surface-variant/80'}`}>
                        {String(cell.d).padStart(2, '0')}
                      </span>
                      {exams && exams.length > 1 && (
                        <span className="text-[9px] text-on-surface-variant/40 font-bold">{exams.length}</span>
                      )}
                    </div>
                    <div className="space-y-1">
                      {exams && exams.slice(0, 2).map((ev, j) => {
                        const s = toneStyles[ev.tone]
                        return (
                          <div key={j}
                            className={`px-1.5 py-1 rounded text-[9px] font-bold tracking-wide truncate ${ev.pulse ? 'pulse-soft' : ''}`}
                            style={{
                              background: s.bg, color: s.fg, borderLeft: `2px solid ${s.bd}`,
                              boxShadow: ev.conflict ? 'inset 0 0 12px rgba(147,0,10,0.4)' : ev.pulse ? `0 0 12px ${s.bd}88` : 'none',
                            }}>
                            {ev.conflict && '⚠ '}{ev.code}
                          </div>
                        )
                      })}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="flex flex-wrap gap-3 mt-5">
            <LegendDot color="#adc6ff" label="Engineering & Sciences" />
            <LegendDot color="#d0bcff" label="Humanities" />
            <LegendDot color="#ffb786" label="Social Sciences" />
            <LegendDot color="#ffb4ab" label="Conflict" pulse />
          </div>
        </section>

        {/* Side insights */}
        <section className="col-span-12 lg:col-span-3 space-y-6">
          <FocusedDayCard day={focusedDay} />
          <InsightsCard />
          <PendingResolutionsCard />
        </section>
      </div>

      {/* FAB */}
      <button
        className="fixed bottom-8 right-8 w-14 h-14 rounded-2xl flex items-center justify-center text-white active:scale-95 transition-all z-50 group"
        style={{
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          boxShadow: '0 0 30px rgba(173,198,255,0.4), 0 12px 30px -10px rgba(139,92,246,0.5)',
        }}
      >
        <Icon name="add" className="text-[26px] group-hover:rotate-90 transition-transform" />
      </button>
    </WorkspaceShell>
  )
}
