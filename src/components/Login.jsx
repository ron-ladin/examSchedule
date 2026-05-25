/**
 * Login.jsx
 * Source: Stitch screen "Syncademic - Sign In"
 * Design freeze: Sora font · Liquid Glass · Electric Blue→Deep Purple gradient
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function Login() {
  const navigate = useNavigate()
  const [form, setForm]           = useState({ email: '', password: '', staySignedIn: false })
  const [showPassword, setShow]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    // TODO: POST /api/auth/login { email, password }
    // On success: store token, navigate('/dashboard')
    setTimeout(() => {
      setLoading(false)
      navigate('/dashboard')
    }, 800)
  }

  const inputStyle = {
    width: '100%',
    padding: '0.75rem 1rem 0.75rem 2.75rem',
    borderRadius: '9999px',
    border: '1.5px solid var(--outline-variant)',
    background: 'var(--surface-container-low)',
    fontFamily: 'Inter, sans-serif',
    fontSize: '0.9rem',
    color: 'var(--on-surface)',
    outline: 'none',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(145deg, #050a1a 0%, #0a0f2e 40%, #140a2e 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Ambient orbs */}
      <div style={{
        position: 'absolute', top: '10%', left: '10%', width: '500px', height: '500px',
        borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '10%', right: '10%', width: '400px', height: '400px',
        borderRadius: '50%', background: 'radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div
        className="glass"
        style={{
          width: '100%',
          maxWidth: '420px',
          borderRadius: '1.5rem',
          padding: '2.5rem',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {/* Logo + branding */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'var(--gradient-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1rem',
              boxShadow: '0 0 24px rgba(59,130,246,0.4)',
            }}
          >
            <span className="material-icons-round" style={{ color: 'white', fontSize: '1.5rem' }}>
              auto_fix_high
            </span>
          </div>
          <h1
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: '1.5rem',
              fontWeight: 800,
              color: 'white',
              letterSpacing: '-0.02em',
              marginBottom: '0.35rem',
            }}
          >
            Syncademic
          </h1>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)' }}>
            Precision academic mastery
          </p>
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: '0.75rem',
              background: 'rgba(186,26,26,0.15)',
              border: '1px solid rgba(186,26,26,0.3)',
              marginBottom: '1rem',
            }}
          >
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: '#fca5a5' }}>{error}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          {/* Email */}
          <div style={{ position: 'relative' }}>
            <span
              className="material-icons-round"
              style={{
                position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)',
                color: 'rgba(255,255,255,0.4)', fontSize: '1.1rem', pointerEvents: 'none',
              }}
            >
              mail
            </span>
            <input
              type="email"
              placeholder="Email Address"
              value={form.email}
              onChange={e => set('email', e.target.value)}
              required
              style={{ ...inputStyle, background: 'rgba(255,255,255,0.06)', border: '1.5px solid rgba(255,255,255,0.12)', color: 'white' }}
              onFocus={e => { e.target.style.borderColor = '#3b82f6'; e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.2)' }}
              onBlur={e  => { e.target.style.borderColor = 'rgba(255,255,255,0.12)'; e.target.style.boxShadow = 'none' }}
            />
          </div>

          {/* Password */}
          <div style={{ position: 'relative' }}>
            <span
              className="material-icons-round"
              style={{
                position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)',
                color: 'rgba(255,255,255,0.4)', fontSize: '1.1rem', pointerEvents: 'none',
              }}
            >
              lock
            </span>
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              value={form.password}
              onChange={e => set('password', e.target.value)}
              required
              style={{ ...inputStyle, background: 'rgba(255,255,255,0.06)', border: '1.5px solid rgba(255,255,255,0.12)', color: 'white', paddingRight: '3rem' }}
              onFocus={e => { e.target.style.borderColor = '#3b82f6'; e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.2)' }}
              onBlur={e  => { e.target.style.borderColor = 'rgba(255,255,255,0.12)'; e.target.style.boxShadow = 'none' }}
            />
            <button
              type="button"
              onClick={() => setShow(p => !p)}
              style={{
                position: 'absolute', right: '1rem', top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              }}
            >
              <span className="material-icons-round" style={{ color: 'rgba(255,255,255,0.4)', fontSize: '1.1rem' }}>
                {showPassword ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>

          {/* Stay signed in + Forgot */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={form.staySignedIn}
                onChange={e => set('staySignedIn', e.target.checked)}
                style={{ accentColor: '#3b82f6' }}
              />
              <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: 'rgba(255,255,255,0.6)' }}>
                Stay signed in
              </span>
            </label>
            <a href="#" style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: 'rgba(255,255,255,0.5)', textDecoration: 'none' }}>
              Forgot?
            </a>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ justifyContent: 'center', opacity: loading ? 0.7 : 1 }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
            {!loading && <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>arrow_forward</span>}
          </button>
        </form>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '1.25rem 0' }}>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.1)' }} />
          <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.75rem', color: 'rgba(255,255,255,0.35)' }}>OR</span>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.1)' }} />
        </div>

        {/* Institution SSO */}
        <button
          className="btn-ghost"
          style={{ width: '100%', justifyContent: 'center' }}
          type="button"
        >
          <span className="material-icons-round" style={{ fontSize: '1rem' }}>business</span>
          Continue with Institution
        </button>

        {/* Sign up link */}
        <p style={{
          textAlign: 'center',
          marginTop: '1.5rem',
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.82rem',
          color: 'rgba(255,255,255,0.45)',
        }}>
          No account?{' '}
          <Link to="/register" style={{ color: '#93c5fd', fontWeight: 600, textDecoration: 'none' }}>
            Sign Up
          </Link>
        </p>
      </div>

      {/* Footer */}
      <p
        style={{
          position: 'absolute', bottom: '1.5rem',
          fontFamily: 'Inter, sans-serif', fontSize: '0.72rem',
          color: 'rgba(255,255,255,0.2)',
        }}
      >
        © 2024 Syncademic. Secure Academic Environment.
      </p>
    </div>
  )
}
