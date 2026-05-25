/**
 * LandingPage.jsx
 * Source: Stitch screen "Syncademic - Premium Landing Page"
 * Design freeze: Sora font · Liquid Glass · Electric Blue→Deep Purple gradient
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

// ── Hero background — dark gradient with glass overlay ─────────────────────
const heroStyle = {
  background: 'linear-gradient(145deg, #050a1a 0%, #0a0f2e 40%, #140a2e 100%)',
  minHeight: '100vh',
  position: 'relative',
  overflow: 'hidden',
}

const glowBlue = {
  position: 'absolute',
  width: '600px',
  height: '600px',
  borderRadius: '50%',
  background: 'radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 70%)',
  pointerEvents: 'none',
}

// ── Feature card data ──────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: 'dynamic_form',
    title: 'Core Algorithmic Resolution',
    desc: 'Backtracking CSP engines with Most-Constrained-Variable heuristics eliminate every student group overlap before a schedule is ever published.',
    chip: 'O(n²) conflict graph',
  },
  {
    icon: 'stream',
    title: 'Lazy Streaming Architecture',
    desc: 'Schedules are yielded as a lazy iterator — results preview in real-time as the solver progresses, without waiting for full completion.',
    chip: 'Live preview',
  },
  {
    icon: 'calendar_month',
    title: 'Universal Controls',
    desc: 'Configure rest days, holiday exclusions, and program filters through the glassmorphic control pane. Changes propagate instantly.',
    chip: 'Glassmorphic UI',
  },
]

// ── Process step data ──────────────────────────────────────────────────────
const STEPS = [
  { num: '01', title: 'Ingest Data Sets',       desc: 'Upload courses.txt, dates.txt, and programs.txt — or enter data manually through the coordinator dashboard.' },
  { num: '02', title: 'Configure Exclusions',   desc: 'Set rest days, holiday windows, and minimum study gaps. The engine respects every institutional constraint.' },
  { num: '03', title: 'Stream Master Schedule', desc: 'The CSP backtracking engine yields conflict-free solutions in real time, ranked by optimality.' },
  { num: '04', title: 'Export & Publish',        desc: 'Download the final schedule as a structured report and submit directly to the registrar.' },
]

// ── FAQ data ───────────────────────────────────────────────────────────────
const FAQS = [
  {
    q: 'Can Syncademic integrate with our existing LMS?',
    a: 'Yes. The platform exposes a REST API compatible with standard LMS exports. Upload your data files directly, or connect via our API adapters for automated ingestion.',
  },
  {
    q: 'What happens if a room or instructor changes last-minute?',
    a: 'Re-run the solver on the updated data set. The CSP engine re-optimizes in seconds, producing a revised conflict-free schedule that respects all existing constraints.',
  },
  {
    q: 'How fast does the engine process large programs?',
    a: 'For typical university programs (50–200 courses, 3–5 programs), the solver resolves in under 10 seconds. The lazy streaming architecture means you see partial results immediately.',
  },
]

// ── Sub-components ─────────────────────────────────────────────────────────

function Nav() {
  return (
    <nav
      className="glass fixed top-0 left-0 right-0 z-50"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', borderRadius: 0 }}
    >
      <div
        style={{
          maxWidth: '1280px',
          margin: '0 auto',
          padding: '0 2rem',
          height: '68px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'var(--gradient-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span className="material-icons-round" style={{ color: 'white', fontSize: '1.1rem' }}>
              auto_fix_high
            </span>
          </div>
          <span
            style={{
              fontFamily: 'Sora, sans-serif',
              fontWeight: 700,
              fontSize: '1.1rem',
              color: 'white',
              letterSpacing: '-0.02em',
            }}
          >
            Syncademic
          </span>
        </div>

        {/* Nav links */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
          {['Platform', 'Resources', 'Pricing'].map(item => (
            <a
              key={item}
              href="#"
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.875rem',
                fontWeight: 500,
                color: 'rgba(255,255,255,0.7)',
                textDecoration: 'none',
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => (e.target.style.color = 'white')}
              onMouseLeave={e => (e.target.style.color = 'rgba(255,255,255,0.7)')}
            >
              {item}
            </a>
          ))}
        </div>

        {/* CTAs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Link to="/login" className="btn-ghost" style={{ padding: '0.5rem 1.25rem', fontSize: '0.85rem' }}>
            Sign In
          </Link>
          <Link to="/register" className="btn-primary" style={{ padding: '0.5rem 1.25rem', fontSize: '0.85rem' }}>
            Join Waitlist
          </Link>
        </div>
      </div>
    </nav>
  )
}

function HeroSection() {
  return (
    <section style={{ ...heroStyle, paddingTop: '68px' }}>
      {/* Ambient glow orbs */}
      <div style={{ ...glowBlue, top: '10%', left: '5%' }} />
      <div style={{ ...glowBlue, top: '20%', right: '5%', background: 'radial-gradient(circle, rgba(139,92,246,0.18) 0%, transparent 70%)' }} />

      <div
        style={{
          maxWidth: '1280px',
          margin: '0 auto',
          padding: '7rem 2rem 5rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {/* Eyebrow chip */}
        <div
          className="chip chip-blue"
          style={{ marginBottom: '1.5rem', background: 'rgba(59,130,246,0.15)', color: '#93c5fd' }}
        >
          <span className="material-icons-round" style={{ fontSize: '0.85rem' }}>auto_awesome</span>
          CSP · Backtracking · MCV Heuristics
        </div>

        {/* Headline */}
        <h1
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: 'clamp(2.5rem, 5vw, 4rem)',
            fontWeight: 800,
            color: 'white',
            lineHeight: 1.1,
            letterSpacing: '-0.03em',
            maxWidth: '820px',
            marginBottom: '1.5rem',
          }}
        >
          Conflict-Free Academic Schedules.{' '}
          <span
            style={{
              background: 'var(--gradient-primary)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Optimized Instantly.
          </span>
        </h1>

        {/* Sub-heading */}
        <p
          style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '1.15rem',
            fontWeight: 400,
            color: 'rgba(255,255,255,0.6)',
            maxWidth: '600px',
            lineHeight: 1.7,
            marginBottom: '2.5rem',
          }}
        >
          Sophisticated constraint-satisfaction algorithms eliminate every student group overlap —
          before a schedule is ever published.
        </p>

        {/* CTAs */}
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          <Link to="/register" className="btn-primary">
            Get Started Now
            <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>arrow_forward</span>
          </Link>
          <a href="#features" className="btn-ghost">
            See How It Works
          </a>
        </div>

        {/* Hero visual — glassmorphic calendar mesh */}
        <div
          className="glass"
          style={{
            marginTop: '4rem',
            width: '100%',
            maxWidth: '900px',
            borderRadius: '1.5rem',
            padding: '2rem',
            display: 'grid',
            gridTemplateColumns: 'repeat(7, 1fr)',
            gap: '0.5rem',
            position: 'relative',
          }}
        >
          {/* Grid header */}
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
            <div
              key={d}
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.65rem',
                color: 'rgba(255,255,255,0.4)',
                textAlign: 'center',
                padding: '0.25rem',
                letterSpacing: '0.05em',
              }}
            >
              {d}
            </div>
          ))}
          {/* Mock calendar cells */}
          {Array.from({ length: 35 }).map((_, i) => {
            const hasExam  = [2, 5, 8, 11, 14, 17, 20, 23, 26].includes(i)
            const conflict = [8, 23].includes(i)
            return (
              <div
                key={i}
                style={{
                  borderRadius: '0.5rem',
                  padding: '0.5rem 0.25rem',
                  minHeight: '48px',
                  background: conflict
                    ? 'rgba(186,26,26,0.2)'
                    : hasExam
                    ? 'linear-gradient(135deg, rgba(59,130,246,0.25), rgba(139,92,246,0.25))'
                    : 'rgba(255,255,255,0.03)',
                  border: conflict
                    ? '1px solid rgba(186,26,26,0.3)'
                    : hasExam
                    ? '1px solid rgba(59,130,246,0.2)'
                    : '1px solid rgba(255,255,255,0.04)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.2rem',
                }}
              >
                <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>
                  {i + 1}
                </span>
                {hasExam && (
                  <span
                    style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.55rem',
                      color: conflict ? '#fca5a5' : '#93c5fd',
                      letterSpacing: '0.03em',
                    }}
                  >
                    {conflict ? '⚠ CS-401' : 'EXAM'}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Social proof */}
      <div
        style={{
          borderTop: '1px solid rgba(255,255,255,0.06)',
          padding: '2rem',
          textAlign: 'center',
        }}
      >
        <p
          style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.8rem',
            color: 'rgba(255,255,255,0.35)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: '1.5rem',
          }}
        >
          Trusted by leading academic institutions
        </p>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '3rem',
            flexWrap: 'wrap',
          }}
        >
          {['Stanford', 'ETH Zürich', 'Oxford', 'MIT', 'Bar-Ilan'].map(name => (
            <span
              key={name}
              style={{
                fontFamily: 'Sora, sans-serif',
                fontSize: '0.9rem',
                fontWeight: 600,
                color: 'rgba(255,255,255,0.3)',
                letterSpacing: '-0.01em',
              }}
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

function FeaturesSection() {
  return (
    <section
      id="features"
      style={{ background: 'var(--surface)', padding: '6rem 2rem' }}
    >
      <div style={{ maxWidth: '1280px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '3.5rem' }}>
          <div className="chip chip-purple" style={{ marginBottom: '1rem', display: 'inline-flex' }}>
            Core Capabilities
          </div>
          <h2
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: 'clamp(1.75rem, 3vw, 2.5rem)',
              fontWeight: 700,
              color: 'var(--on-surface)',
              letterSpacing: '-0.02em',
            }}
          >
            Built for{' '}
            <span
              style={{
                background: 'var(--gradient-primary)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              academic complexity
            </span>
          </h2>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {FEATURES.map(f => (
            <div key={f.title} className="card" style={{ padding: '2rem', transition: 'transform 0.2s, box-shadow 0.2s' }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'translateY(-4px)'
                e.currentTarget.style.boxShadow = '0 20px 40px rgba(59,130,246,0.12)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = 'var(--glass-shadow)'
              }}
            >
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'var(--gradient-glow)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1.25rem',
                  border: '1px solid var(--outline-variant)',
                }}
              >
                <span className="material-icons-round gradient-text" style={{ fontSize: '1.4rem' }}>
                  {f.icon}
                </span>
              </div>
              <h3
                style={{
                  fontFamily: 'Sora, sans-serif',
                  fontSize: '1.05rem',
                  fontWeight: 700,
                  color: 'var(--on-surface)',
                  marginBottom: '0.75rem',
                  letterSpacing: '-0.01em',
                }}
              >
                {f.title}
              </h3>
              <p
                style={{
                  fontFamily: 'Inter, sans-serif',
                  fontSize: '0.9rem',
                  color: 'var(--on-surface-variant)',
                  lineHeight: 1.65,
                  marginBottom: '1rem',
                }}
              >
                {f.desc}
              </p>
              <span className="chip chip-blue">{f.chip}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function ProcessSection() {
  return (
    <section
      style={{
        background: 'var(--surface-container-low)',
        padding: '6rem 2rem',
        borderTop: '1px solid var(--outline-variant)',
        borderBottom: '1px solid var(--outline-variant)',
      }}
    >
      <div style={{ maxWidth: '900px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '3.5rem' }}>
          <h2
            style={{
              fontFamily: 'Sora, sans-serif',
              fontSize: 'clamp(1.75rem, 3vw, 2.5rem)',
              fontWeight: 700,
              color: 'var(--on-surface)',
              letterSpacing: '-0.02em',
            }}
          >
            From data to schedule in{' '}
            <span
              style={{
                background: 'var(--gradient-primary)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              four steps
            </span>
          </h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {STEPS.map((step, i) => (
            <div
              key={step.num}
              style={{
                display: 'flex',
                gap: '1.5rem',
                paddingBottom: i < STEPS.length - 1 ? '0' : '0',
              }}
            >
              {/* Step number + connector */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <div
                  style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    background: 'var(--gradient-primary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: 'white',
                    flexShrink: 0,
                    boxShadow: '0 0 16px rgba(59,130,246,0.3)',
                  }}
                >
                  {step.num}
                </div>
                {i < STEPS.length - 1 && (
                  <div className="step-connector" style={{ height: '60px' }} />
                )}
              </div>

              {/* Content */}
              <div style={{ paddingBottom: '2rem', paddingTop: '0.4rem' }}>
                <h3
                  style={{
                    fontFamily: 'Sora, sans-serif',
                    fontSize: '1.05rem',
                    fontWeight: 700,
                    color: 'var(--on-surface)',
                    marginBottom: '0.4rem',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {step.title}
                </h3>
                <p
                  style={{
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '0.9rem',
                    color: 'var(--on-surface-variant)',
                    lineHeight: 1.65,
                  }}
                >
                  {step.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section style={{ background: 'var(--surface)', padding: '6rem 2rem', textAlign: 'center' }}>
      <div style={{ maxWidth: '700px', margin: '0 auto' }}>
        <div
          style={{
            background: 'linear-gradient(145deg, #050a1a, #0a0f2e)',
            borderRadius: '2rem',
            padding: '4rem 3rem',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div style={{ ...glowBlue, top: '-30%', left: '-20%', width: '400px', height: '400px' }} />
          <div
            style={{
              ...glowBlue,
              top: '-30%',
              right: '-20%',
              width: '400px',
              height: '400px',
              background: 'radial-gradient(circle, rgba(139,92,246,0.2) 0%, transparent 70%)',
            }}
          />
          <div style={{ position: 'relative', zIndex: 1 }}>
            <h2
              style={{
                fontFamily: 'Sora, sans-serif',
                fontSize: 'clamp(1.5rem, 3vw, 2.2rem)',
                fontWeight: 800,
                color: 'white',
                marginBottom: '1rem',
                letterSpacing: '-0.02em',
              }}
            >
              Ready to eliminate scheduling conflicts forever?
            </h2>
            <p
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '1rem',
                color: 'rgba(255,255,255,0.6)',
                marginBottom: '2rem',
                lineHeight: 1.65,
              }}
            >
              Join coordinators at leading universities who run conflict-free exam periods with Syncademic.
            </p>
            <Link to="/register" className="btn-primary">
              Optimize Your Institution
              <span className="material-icons-round" style={{ fontSize: '1.1rem' }}>arrow_forward</span>
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function FaqSection() {
  const [openIdx, setOpenIdx] = useState(null)

  return (
    <section
      style={{
        background: 'var(--surface-container-low)',
        padding: '6rem 2rem',
        borderTop: '1px solid var(--outline-variant)',
      }}
    >
      <div style={{ maxWidth: '700px', margin: '0 auto' }}>
        <h2
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: 'clamp(1.5rem, 3vw, 2rem)',
            fontWeight: 700,
            color: 'var(--on-surface)',
            marginBottom: '2.5rem',
            letterSpacing: '-0.02em',
          }}
        >
          Frequently Asked Questions
        </h2>

        <div className="card" style={{ overflow: 'hidden', padding: 0 }}>
          {FAQS.map((faq, i) => (
            <div key={i} className="faq-item">
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                style={{
                  width: '100%',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '1.25rem 1.5rem',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  gap: '1rem',
                }}
              >
                <span
                  style={{
                    fontFamily: 'Sora, sans-serif',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    color: 'var(--on-surface)',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {faq.q}
                </span>
                <span
                  className="material-icons-round"
                  style={{
                    fontSize: '1.25rem',
                    color: 'var(--outline)',
                    transition: 'transform 0.2s',
                    transform: openIdx === i ? 'rotate(180deg)' : 'rotate(0)',
                    flexShrink: 0,
                  }}
                >
                  expand_more
                </span>
              </button>
              {openIdx === i && (
                <div
                  style={{
                    padding: '0 1.5rem 1.25rem',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: '0.9rem',
                    color: 'var(--on-surface-variant)',
                    lineHeight: 1.7,
                  }}
                >
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer
      style={{
        background: 'var(--on-surface)',
        padding: '2rem',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          maxWidth: '1280px',
          margin: '0 auto',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <span
          style={{
            fontFamily: 'Sora, sans-serif',
            fontSize: '0.85rem',
            fontWeight: 600,
            color: 'rgba(255,255,255,0.4)',
          }}
        >
          © 2024 Syncademic Labs
        </span>
        <div style={{ display: 'flex', gap: '2rem' }}>
          {['Privacy', 'Terms', 'API Docs', 'Support'].map(link => (
            <a
              key={link}
              href="#"
              style={{
                fontFamily: 'Inter, sans-serif',
                fontSize: '0.8rem',
                color: 'rgba(255,255,255,0.35)',
                textDecoration: 'none',
              }}
              onMouseEnter={e => (e.target.style.color = 'rgba(255,255,255,0.7)')}
              onMouseLeave={e => (e.target.style.color = 'rgba(255,255,255,0.35)')}
            >
              {link}
            </a>
          ))}
        </div>
      </div>
    </footer>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div style={{ minHeight: '100vh' }}>
      <Nav />
      <HeroSection />
      <FeaturesSection />
      <ProcessSection />
      <CtaSection />
      <FaqSection />
      <Footer />
    </div>
  )
}
