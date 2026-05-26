import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Icon, AmbientOrbs, BrandMark } from './Shared'

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

export default function Login() {
  const navigate = useNavigate()
  const [showPw, setShowPw] = useState(false)
  const [email, setEmail] = useState('a.thorne@northfield.edu')
  const [password, setPassword] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    navigate('/dashboard')
  }

  return (
    <AuthShell>
      <div className="w-full max-w-[440px] screen-anim">
        <div className="glass rounded-3xl p-8 md:p-10 flex flex-col items-center">
          <div className="mb-9 text-center">
            <h1 className="text-[28px] font-extrabold tracking-tight mb-2">Welcome back</h1>
            <p className="text-on-surface-variant/75 text-[14px]">Precision academic mastery.</p>
          </div>

          <form onSubmit={handleSubmit} className="w-full space-y-5">
            <div>
              <label className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/70 font-semibold ml-1 block mb-2">
                Email address
              </label>
              <div className="input-shell relative flex items-center bg-surface-container-lowest/60 border border-white/[0.08] rounded-xl transition-all">
                <Icon name="mail" className="absolute left-4 text-on-surface-variant/40" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="name@university.edu"
                  className="w-full bg-transparent border-none py-3.5 pl-12 pr-4 text-on-surface text-[14px] focus:outline-none placeholder:text-on-surface-variant/30"
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center ml-1 mb-2">
                <label className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/70 font-semibold">Password</label>
                <a className="text-[10px] uppercase tracking-[0.12em] text-primary hover:text-secondary font-semibold" href="#">Forgot?</a>
              </div>
              <div className="input-shell relative flex items-center bg-surface-container-lowest/60 border border-white/[0.08] rounded-xl transition-all">
                <Icon name="lock" className="absolute left-4 text-on-surface-variant/40" />
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-transparent border-none py-3.5 pl-12 pr-12 text-on-surface text-[14px] focus:outline-none placeholder:text-on-surface-variant/30"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-4 text-on-surface-variant/50 hover:text-on-surface"
                >
                  <Icon name={showPw ? 'visibility_off' : 'visibility'} />
                </button>
              </div>
            </div>

            <div className="flex items-center gap-3 ml-1">
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  defaultChecked
                  className="h-4 w-4 rounded border-white/20 bg-white/5 text-primary focus:ring-primary focus:ring-offset-0"
                />
                <span className="text-[13px] text-on-surface-variant">Stay signed in</span>
              </label>
            </div>

            <button
              type="submit"
              className="btn-grad w-full py-4 rounded-full font-semibold uppercase tracking-[0.08em] text-[13px] flex items-center justify-center gap-2 group"
            >
              Sign In
              <Icon name="arrow_forward" className="text-[18px] group-hover:translate-x-1 transition-transform" />
            </button>
          </form>

          <div className="w-full flex items-center my-7 gap-4">
            <div className="flex-grow h-px bg-white/10" />
            <span className="text-[10px] uppercase tracking-[0.2em] text-on-surface-variant/40 font-semibold">OR</span>
            <div className="flex-grow h-px bg-white/10" />
          </div>

          <button className="w-full flex items-center justify-center gap-3 py-3 rounded-xl border border-white/[0.08] bg-white/5 hover:bg-white/[0.08] transition-colors">
            <Icon name="apartment" className="text-primary" />
            <span className="text-[13px] text-on-surface">Continue with Institution SSO</span>
          </button>

          <p className="text-[13px] text-on-surface-variant mt-7 text-center">
            Don't have an account?{' '}
            <button onClick={() => navigate('/register')} className="text-primary font-bold hover:underline ml-1.5">
              Sign up
            </button>
          </p>
        </div>
      </div>
    </AuthShell>
  )
}
