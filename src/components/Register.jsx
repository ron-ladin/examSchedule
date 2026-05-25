/**
 * Register.jsx
 * Source: Stitch screen "Syncademic - Create Account"
 * Design freeze: Sora font · Liquid Glass · Electric Blue→Deep Purple gradient
 *
 * User role options map to institutional coordinator types.
 * On success, navigates to /dashboard.
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { USER_ROLES } from '../models/types'

const STRENGTH = { weak: '#ba1a1a', moderate: '#f59e0b', strong: '#10b981' }

function getStrength(pw) {
  if (!pw)          return null
  if (pw.length < 6) return 'weak'
  if (pw.length < 10 || !/[^a-zA-Z0-9]/.test(pw)) return 'moderate'
  return 'strong'
}

export default function Register() {
  const navigate = useNavigate()
  const [step, setStep]     = useState('form')  // 'form' | 'success'
  const [loading, setLoading] = useState(false)
  const [form, setForm]     = useState({
    firstName:   '',
    lastName:    '',
    dob:         '',
    email:       '',
    phone:       '',
    institution: '',
    role:        '',
    password:    '',
  })

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))
  const strength = getStrength(form.password)

  const inputStyle = (extra = {}) => ({
    width: '100%',
    padding: '0.7rem 1rem',
    borderRadius: '0.75rem',
    border: '1.5px solid var(--outline-variant)',
    background: 'var(--surface-container-low)',
    fontFamily: 'Inter, sans-serif',
    fontSize: '0.875rem',
    color: 'var(--on-surface)',
    outline: 'none',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    ...extra,
  })

  const focusHandler = e => { e.target.style.borderColor = '#3b82f6'; e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.15)' }
  const blurHandler  = e => { e.target.style.borderColor = 'var(--outline-variant)'; e.target.style.boxShadow = 'none' }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    // TODO: POST /api/auth/register { ...form }
    // On success → create coordinator session → setStep('success')
    setTimeout(() => {
      setLoading(false)
      setStep('success')
    }, 900)
  }

  const labelStyle = {
    fontFamily: 'Inter, sans-serif',
    fontSize: '0.8rem',
    fontWeight: 600,
    color: 'var(--on-surface-variant)',
    display: 'block',
    marginBottom: '0.35rem',
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--surface-container-low)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        padding: '3rem 1.5rem',
      }}
    >
      <div style={{ width: '100%', maxWidth: '520px' }}>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '2rem', justifyContent: 'center' }}>
          <div
            style={{
              width: '36px', height: '36px', borderRadius: '9px',
              background: 'var(--gradient-primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <span className="material-icons-round" style={{ color: 'white', fontSize: '1.2rem' }}>auto_fix_high</span>
          </div>
          <span style={{ fontFamily: 'Sora, sans-serif', fontWeight: 700, fontSize: '1.1rem', color: 'var(--on-surface)', letterSpacing: '-0.02em' }}>
            Syncademic
          </span>
        </div>

        {step === 'success' ? (
          /* ── Success state ──────────────────────────────────────────── */
          <div className="card" style={{ padding: '3rem', textAlign: 'center' }}>
            <div
              style={{
                width: '64px', height: '64px', borderRadius: '50%',
                background: 'rgba(16,185,129,0.1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 1.5rem',
              }}
            >
              <span className="material-icons-round" style={{ color: 'var(--success)', fontSize: '2rem' }}>check_circle</span>
            </div>
            <h2
              style={{
                fontFamily: 'Sora, sans-serif', fontSize: '1.3rem', fontWeight: 700,
                color: 'var(--on-surface)', marginBottom: '0.75rem', letterSpacing: '-0.02em',
              }}
            >
              Account Created
            </h2>
            <p
              style={{
                fontFamily: 'Inter, sans-serif', fontSize: '0.88rem',
                color: 'var(--on-surface-variant)', lineHeight: 1.65, marginBottom: '2rem',
              }}
            >
              Your coordinator credentials have been synchronized.<br />
              Welcome to the Syncademic ecosystem.
            </p>
            <button className="btn-primary" style={{ justifyContent: 'center' }} onClick={() => navigate('/dashboard')}>
              Enter Dashboard
              <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>arrow_forward</span>
            </button>
          </div>
        ) : (
          /* ── Registration form ─────────────────────────────────────── */
          <div className="card" style={{ padding: '2.5rem' }}>
            <h1
              style={{
                fontFamily: 'Sora, sans-serif', fontSize: '1.5rem', fontWeight: 800,
                color: 'var(--on-surface)', letterSpacing: '-0.02em', marginBottom: '0.4rem',
              }}
            >
              Create Coordinator Account
            </h1>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.84rem', color: 'var(--on-surface-variant)', marginBottom: '2rem', lineHeight: 1.5 }}>
              Elevate your institution's academic flow with Syncademic's premier engine.
            </p>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>

              {/* Name row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label style={labelStyle}>First Name</label>
                  <input
                    type="text" required value={form.firstName}
                    onChange={e => set('firstName', e.target.value)}
                    style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Last Name</label>
                  <input
                    type="text" required value={form.lastName}
                    onChange={e => set('lastName', e.target.value)}
                    style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                  />
                </div>
              </div>

              {/* DOB */}
              <div>
                <label style={labelStyle}>
                  <span className="material-icons-round" style={{ fontSize: '0.9rem', verticalAlign: 'middle', marginRight: '0.25rem' }}>calendar_today</span>
                  Date of Birth
                </label>
                <input
                  type="date" value={form.dob} onChange={e => set('dob', e.target.value)}
                  style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                />
              </div>

              {/* Work email */}
              <div>
                <label style={labelStyle}>Work Email</label>
                <input
                  type="email" required value={form.email}
                  onChange={e => set('email', e.target.value)}
                  style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                />
              </div>

              {/* Phone */}
              <div>
                <label style={labelStyle}>Phone Number</label>
                <input
                  type="tel" value={form.phone}
                  onChange={e => set('phone', e.target.value)}
                  style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                />
              </div>

              {/* Institution */}
              <div>
                <label style={labelStyle}>
                  <span className="material-icons-round" style={{ fontSize: '0.9rem', verticalAlign: 'middle', marginRight: '0.25rem' }}>school</span>
                  Academic Institution
                </label>
                <input
                  type="text" required value={form.institution}
                  onChange={e => set('institution', e.target.value)}
                  style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                />
              </div>

              {/* Role dropdown */}
              <div>
                <label style={labelStyle}>User Role</label>
                <div style={{ position: 'relative' }}>
                  <select
                    value={form.role} required
                    onChange={e => set('role', e.target.value)}
                    style={{ ...inputStyle(), appearance: 'none', paddingRight: '2.5rem', cursor: 'pointer' }}
                    onFocus={focusHandler} onBlur={blurHandler}
                  >
                    <option value="">Select a role...</option>
                    {USER_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <span
                    className="material-icons-round"
                    style={{
                      position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)',
                      color: 'var(--outline)', fontSize: '1.2rem', pointerEvents: 'none',
                    }}
                  >
                    expand_more
                  </span>
                </div>
              </div>

              {/* Password */}
              <div>
                <label style={labelStyle}>Password</label>
                <input
                  type="password" required value={form.password}
                  onChange={e => set('password', e.target.value)}
                  style={inputStyle()} onFocus={focusHandler} onBlur={blurHandler}
                />
                {/* Strength indicator */}
                {strength && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.4rem' }}>
                    {['weak', 'moderate', 'strong'].map(s => (
                      <div
                        key={s}
                        style={{
                          height: '3px',
                          flex: 1,
                          borderRadius: '99px',
                          background:
                            (s === 'weak') ||
                            (s === 'moderate' && (strength === 'moderate' || strength === 'strong')) ||
                            (s === 'strong' && strength === 'strong')
                              ? STRENGTH[strength]
                              : 'var(--outline-variant)',
                          transition: 'background 0.2s',
                        }}
                      />
                    ))}
                    <span
                      style={{
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: '0.65rem',
                        fontWeight: 500,
                        color: STRENGTH[strength],
                        letterSpacing: '0.04em',
                        textTransform: 'uppercase',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Security {strength}
                    </span>
                  </div>
                )}
              </div>

              {/* Terms */}
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.78rem', color: 'var(--outline)', lineHeight: 1.5 }}>
                By registering, you agree to our{' '}
                <a href="#" style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 500 }}>Terms of Excellence</a>.
              </p>

              {/* Submit */}
              <button
                type="submit"
                className="btn-primary"
                disabled={loading}
                style={{ justifyContent: 'center', opacity: loading ? 0.7 : 1 }}
              >
                {loading ? 'Creating account...' : 'Create Coordinator Account'}
              </button>
            </form>

            <p style={{ textAlign: 'center', marginTop: '1.5rem', fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: 'var(--on-surface-variant)' }}>
              Already have an account?{' '}
              <Link to="/login" style={{ color: 'var(--primary)', fontWeight: 600, textDecoration: 'none' }}>Log In</Link>
            </p>
          </div>
        )}

        <p style={{ textAlign: 'center', marginTop: '1.5rem', fontFamily: 'Inter, sans-serif', fontSize: '0.72rem', color: 'var(--outline)' }}>
          © 2024 Syncademic.
        </p>
      </div>
    </div>
  )
}
