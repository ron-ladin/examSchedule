import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import confetti from 'canvas-confetti'
import { Icon, AmbientOrbs, BrandMark, Chip, GradButton } from './Shared'

function AuthShell({ children }) {
  return (
    <div className="relative min-h-screen flex flex-col">
      <AmbientOrbs variant="auth" />
      <header className="relative z-10 flex justify-between items-center px-6 md:px-12 py-6">
        <BrandMark size={38} />
      </header>
      <main className="relative z-10 flex-1 flex items-center justify-center py-10 px-5">
        {children}
      </main>
      <footer className="relative z-10 px-12 py-6 text-center text-[10px] uppercase tracking-[0.22em] text-on-surface-variant/40">
        © 2026 Syncademic · Secure academic environment
      </footer>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="space-y-2">
      <label className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/70 font-semibold block px-1">{label}</label>
      {children}
    </div>
  )
}

function SuccessOverlay({ onContinue }) {
  useEffect(() => {
    const burst = (origin) => confetti({
      particleCount: 80, spread: 70, startVelocity: 45,
      origin, colors: ['#adc6ff', '#d0bcff', '#ffb786', '#3b82f6', '#8b5cf6', '#ffffff'],
      ticks: 250,
    })
    const t1 = setTimeout(() => {
      burst({ x: 0.25, y: 0.4 })
      burst({ x: 0.75, y: 0.4 })
    }, 200)
    const t2 = setTimeout(() => burst({ x: 0.5, y: 0.3 }), 450)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-6 screen-anim"
      style={{ background: 'rgba(6,14,32,0.85)', backdropFilter: 'blur(40px)' }}
    >
      <div className="text-center max-w-md">
        <div className="relative inline-block mb-7">
          <div className="absolute inset-0 bg-primary/30 blur-3xl rounded-full animate-pulse" />
          <div
            className="relative w-24 h-24 rounded-3xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
              boxShadow: '0 20px 60px -10px rgba(139,92,246,0.55), inset 0 1px 0 rgba(255,255,255,0.3)',
            }}
          >
            <Icon name="check_circle" fill className="text-white text-[44px]" />
          </div>
        </div>
        <h2 className="text-[32px] font-extrabold tracking-tight mb-3">Registration complete</h2>
        <p className="text-on-surface-variant/75 text-[14px] mb-9 leading-relaxed">
          Your coordinator credentials have been synchronized. Welcome to the Syncademic ecosystem.
        </p>
        <GradButton size="md" iconAfter="arrow_forward" onClick={onContinue}>Enter dashboard</GradButton>
      </div>
    </div>
  )
}

export default function Register() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [showSuccess, setShowSuccess] = useState(false)
  const [data, setData] = useState({
    firstName: '', lastName: '', dob: '',
    email: '', phone: '', institution: '', role: 'exam_coord',
    password: '',
  })

  const setField = (k, v) => setData(d => ({ ...d, [k]: v }))

  const strength = useMemo(() => {
    const v = data.password || ''
    let s = 0
    if (v.length > 5) s = 33
    if (v.length > 8 && /[A-Z]/.test(v)) s = 66
    if (v.length > 10 && /[0-9]/.test(v) && /[^A-Za-z0-9]/.test(v)) s = 100
    if (s <= 33) return { pct: Math.max(s, 5), label: 'Weak',     color: '#ffb4ab' }
    if (s <= 66) return { pct: s,              label: 'Moderate', color: '#adc6ff' }
    return              { pct: s,              label: 'Superior', color: '#d0bcff' }
  }, [data.password])

  function handleSubmit(e) {
    e.preventDefault()
    setShowSuccess(true)
  }

  return (
    <AuthShell>
      <div className="w-full max-w-2xl screen-anim">
        <div className={`glass rounded-3xl p-8 md:p-12 relative overflow-hidden transition-all duration-500 ${showSuccess ? 'opacity-0 scale-95 pointer-events-none' : ''}`}>
          <div className="mb-7">
            <Chip tone="secondary" className="mb-4">Step {step + 1} of 3</Chip>
            <h1 className="text-[28px] md:text-[32px] font-extrabold tracking-tight mb-2">Create coordinator account</h1>
            <p className="text-on-surface-variant/75 text-[14px]">Elevate your institution's academic flow with the Syncademic engine.</p>
          </div>

          {/* Stepper */}
          <div className="flex items-center gap-2 mb-9">
            {['Identity', 'Institution', 'Security'].map((label, i) => {
              const active = i === step, done = i < step
              return (
                <div key={label} className="flex-1 flex items-center gap-2">
                  <div
                    className="flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] uppercase tracking-widest font-semibold transition-all"
                    style={done || active
                      ? { background: 'rgba(173,198,255,0.10)', color: '#adc6ff', border: '1px solid rgba(173,198,255,0.25)' }
                      : { color: 'rgba(218,226,253,0.4)', border: '1px solid rgba(255,255,255,0.05)' }}
                  >
                    <span className="w-4 h-4 rounded-full flex items-center justify-center text-[9px]"
                      style={{
                        background: done ? 'linear-gradient(135deg,#3b82f6,#8b5cf6)' : active ? 'rgba(173,198,255,0.2)' : 'rgba(255,255,255,0.04)',
                        color: done ? '#fff' : active ? '#adc6ff' : 'rgba(218,226,253,0.4)',
                      }}>
                      {done ? <Icon name="check" className="text-[10px]" /> : i + 1}
                    </span>
                    {label}
                  </div>
                  {i < 2 && <div className={`flex-1 h-px ${i < step ? 'bg-primary/40' : 'bg-white/[0.08]'}`} />}
                </div>
              )
            })}
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {step === 0 && (
              <div className="space-y-5 screen-anim">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <Field label="First name">
                    <input className="liquid-input w-full rounded-lg px-4 py-3 text-[14px]"
                      value={data.firstName} onChange={e => setField('firstName', e.target.value)} placeholder="Aris" required />
                  </Field>
                  <Field label="Last name">
                    <input className="liquid-input w-full rounded-lg px-4 py-3 text-[14px]"
                      value={data.lastName} onChange={e => setField('lastName', e.target.value)} placeholder="Thorne" required />
                  </Field>
                </div>
                <Field label="Date of birth">
                  <div className="relative">
                    <input type="date" className="liquid-input w-full rounded-lg px-4 py-3 text-[14px] pr-12"
                      value={data.dob} onChange={e => setField('dob', e.target.value)} required />
                    <Icon name="calendar_today" className="absolute right-4 top-1/2 -translate-y-1/2 text-primary pointer-events-none" />
                  </div>
                </Field>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-5 screen-anim">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <Field label="Work email">
                    <input type="email" className="liquid-input w-full rounded-lg px-4 py-3 text-[14px]"
                      value={data.email} onChange={e => setField('email', e.target.value)} placeholder="coordinator@university.edu" required />
                  </Field>
                  <Field label="Phone">
                    <input type="tel" className="liquid-input w-full rounded-lg px-4 py-3 text-[14px]"
                      value={data.phone} onChange={e => setField('phone', e.target.value)} placeholder="+1 (555) 000-0000" />
                  </Field>
                </div>
                <Field label="Academic institution">
                  <div className="relative">
                    <input className="liquid-input w-full rounded-lg pl-12 pr-4 py-3 text-[14px]"
                      value={data.institution} onChange={e => setField('institution', e.target.value)} placeholder="University name" required />
                    <Icon name="school" className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant/40" />
                  </div>
                </Field>
                <Field label="Professional role">
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { v: 'dept_chair', l: 'Department Chair',  i: 'groups'                },
                      { v: 'exam_coord', l: 'Exam Coordinator',  i: 'auto_fix_high'          },
                      { v: 'registrar',  l: 'Registrar',         i: 'verified_user'          },
                      { v: 'admin',      l: 'Faculty Admin',     i: 'admin_panel_settings'   },
                    ].map(opt => {
                      const active = data.role === opt.v
                      return (
                        <button key={opt.v} type="button" onClick={() => setField('role', opt.v)}
                          className="flex items-center gap-3 px-4 py-3 rounded-lg transition-all text-left"
                          style={{
                            background: active ? 'rgba(173,198,255,0.08)' : 'rgba(255,255,255,0.02)',
                            border: `1px solid ${active ? 'rgba(173,198,255,0.35)' : 'rgba(255,255,255,0.06)'}`,
                            boxShadow: active ? '0 0 18px rgba(173,198,255,0.18)' : 'none',
                          }}>
                          <Icon name={opt.i} className={active ? 'text-primary' : 'text-on-surface-variant/60'} />
                          <span className={`text-[13px] font-semibold ${active ? 'text-on-surface' : 'text-on-surface-variant'}`}>{opt.l}</span>
                        </button>
                      )
                    })}
                  </div>
                </Field>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-5 screen-anim">
                <Field label="Password">
                  <input type="password" className="liquid-input w-full rounded-lg px-4 py-3 text-[14px]"
                    value={data.password} onChange={e => setField('password', e.target.value)} required />
                </Field>
                <div className="px-1">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/70 font-semibold">Security strength</span>
                    <span className="text-[10px] uppercase tracking-[0.18em] font-semibold" style={{ color: strength.color }}>{strength.label}</span>
                  </div>
                  <div className="w-full bg-white/5 rounded-full h-1 overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${strength.pct}%`, background: strength.color, boxShadow: `0 0 12px ${strength.color}66` }} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-4">
                    {[
                      { ok: data.password.length > 8,          t: '8+ characters'   },
                      { ok: /[A-Z]/.test(data.password),        t: 'Uppercase letter' },
                      { ok: /[0-9]/.test(data.password),        t: 'Number'          },
                      { ok: /[^A-Za-z0-9]/.test(data.password), t: 'Special symbol'  },
                    ].map((c, i) => (
                      <div key={i} className="flex items-center gap-2 text-[11px]" style={{ color: c.ok ? '#adc6ff' : 'rgba(218,226,253,0.4)' }}>
                        <Icon name={c.ok ? 'check_circle' : 'radio_button_unchecked'} fill={c.ok} className="text-[14px]" />
                        {c.t}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex items-start gap-3 mt-2 px-1">
                  <input type="checkbox" defaultChecked required className="mt-1 h-4 w-4 rounded border-white/20 bg-white/5 text-primary focus:ring-primary focus:ring-offset-0" />
                  <span className="text-[12px] text-on-surface-variant/75 leading-relaxed">
                    I agree to the <a className="text-primary hover:underline" href="#">Terms of Excellence</a> and consent to processing of institutional data under FERPA / GDPR.
                  </span>
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-4">
              {step > 0 && (
                <button type="button" onClick={() => setStep(s => s - 1)}
                  className="px-6 py-3.5 rounded-full border border-white/10 text-on-surface-variant hover:bg-white/5 transition-all text-[12px] uppercase tracking-[0.08em] font-semibold flex items-center gap-2">
                  <Icon name="arrow_back" className="text-[16px]" />
                  Back
                </button>
              )}
              {step < 2 ? (
                <button type="button" onClick={() => setStep(s => s + 1)}
                  className="btn-grad flex-1 py-3.5 rounded-full font-semibold uppercase tracking-[0.08em] text-[12px] flex items-center justify-center gap-2">
                  Continue
                  <Icon name="arrow_forward" className="text-[16px]" />
                </button>
              ) : (
                <button type="submit"
                  className="btn-grad flex-1 py-3.5 rounded-full font-semibold uppercase tracking-[0.08em] text-[12px] flex items-center justify-center gap-2">
                  Create coordinator account
                  <Icon name="auto_awesome" className="text-[16px]" />
                </button>
              )}
            </div>
          </form>

          <p className="mt-7 text-center text-[12px] text-on-surface-variant/60">
            Already onboard?{' '}
            <button onClick={() => navigate('/login')} className="text-primary font-bold hover:underline">Sign in</button>
          </p>
        </div>
      </div>

      {showSuccess && <SuccessOverlay onContinue={() => navigate('/dashboard')} />}
    </AuthShell>
  )
}
