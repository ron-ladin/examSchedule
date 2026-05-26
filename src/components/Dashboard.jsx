import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useScheduler } from '../hooks/useScheduler'
import { useToast } from '../hooks/useToast'
import { ToastContainer } from './Toast'
import { api, ApiError } from '../api/client'
import { DATA_FILES } from '../models/types'
import ProgrammePanel from './ProgrammePanel'
import CourseAccordion from './CourseAccordion'
import ExamPeriodCalendar from './ExamPeriodCalendar'
import { Icon, Chip, GradButton, GhostButton, WorkspaceShell, useCurrent } from './Shared'

/* ── Upload card config ─────────────────────────────────────────── */
const UPLOAD_CARDS = [
  { key: 'courses',  icon: 'inventory_2',  title: 'Courses Inventory',   tone: 'secondary',
    blurb: 'Upload your courses list with program offerings, instructors, and evaluation types.',
    fileName: DATA_FILES.COURSES, accept: '.txt,.csv' },
  { key: 'dates',   icon: 'date_range',   title: 'Exam Periods',         tone: 'tertiary',
    blurb: 'Upload the exam window definitions — semester dates, moedim ranges, and exclusions.',
    fileName: DATA_FILES.DATES,   accept: '.txt,.csv' },
  { key: 'programs',icon: 'group',        title: 'Program Selection',    tone: 'primary',
    blurb: 'Upload the list of program IDs to include in this scheduling run.',
    fileName: DATA_FILES.PROGRAMS,accept: '.txt,.csv' },
]

const UPLOAD_FN = {
  courses:  (file) => api.uploadCourses(file),
  dates:    (file) => api.uploadPeriods(file),
  programs: () => Promise.resolve({ message: 'Programs file stored locally.' }),
}

function DropZone({ tone, label, fileName, onSelect, uploading }) {
  const [drag, setDrag] = useState(false)
  const inputRef = useRef(null)
  const tones = {
    primary:   { fg: '#adc6ff', glow: 'rgba(173,198,255,0.30)' },
    secondary: { fg: '#d0bcff', glow: 'rgba(208,188,255,0.30)' },
    tertiary:  { fg: '#ffb786', glow: 'rgba(255,183,134,0.30)' },
  }
  const t = tones[tone]
  return (
    <div
      onDragEnter={e => { e.preventDefault(); setDrag(true) }}
      onDragOver={e => e.preventDefault()}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onSelect(f) }}
      onClick={() => inputRef.current?.click()}
      className="w-full rounded-2xl py-7 px-5 flex flex-col items-center gap-2 cursor-pointer relative overflow-hidden transition-all"
      style={{
        border: `2px dashed ${drag ? t.fg : 'rgba(255,255,255,0.10)'}`,
        background: drag ? `radial-gradient(circle at center, ${t.glow}, transparent 70%)` : fileName ? 'rgba(173,198,255,0.04)' : 'transparent',
      }}
    >
      <input ref={inputRef} type="file" className="hidden" onChange={e => e.target.files[0] && onSelect(e.target.files[0])} />
      {uploading ? (
        <>
          <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <span className="text-[11px] text-primary font-semibold tracking-widest uppercase">Uploading…</span>
        </>
      ) : fileName ? (
        <>
          <Icon name="check_circle" fill className="text-[26px]" style={{ color: t.fg }} />
          <span className="text-[12px] font-bold text-on-surface">{fileName.name || fileName}</span>
          <span className="text-[10px] text-on-surface-variant/60">Click to replace</span>
        </>
      ) : (
        <>
          <Icon name="upload_file" className="text-on-surface-variant/50 text-[26px]" />
          <span className="text-[10px] uppercase tracking-[0.16em] font-semibold text-on-surface-variant/70">{label}</span>
        </>
      )}
    </div>
  )
}

function DataCard({ config, file, uploading, onSelect }) {
  const tones = {
    primary:   { fg: '#adc6ff', glow: 'rgba(173,198,255,0.18)' },
    secondary: { fg: '#d0bcff', glow: 'rgba(208,188,255,0.18)' },
    tertiary:  { fg: '#ffb786', glow: 'rgba(255,183,134,0.18)' },
  }
  const t = tones[config.tone]
  return (
    <div className="glass glass-hover rounded-3xl p-7 flex flex-col group relative overflow-hidden">
      <div className="absolute -top-20 -right-20 w-48 h-48 rounded-full pointer-events-none" style={{ background: t.glow, filter: 'blur(60px)' }} />
      <div className="relative">
        <div className="w-14 h-14 rounded-2xl glass-inner flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-500"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)' }}>
          <Icon name={config.icon} className="text-[26px]" style={{ color: t.fg }} />
        </div>
        <h3 className="text-[22px] font-semibold mb-3">{config.title}</h3>
        <p className="text-on-surface-variant/70 text-[13px] mb-6 leading-relaxed">{config.blurb}</p>
        <DropZone tone={config.tone} label="Drop file here" fileName={file} onSelect={onSelect} uploading={uploading} />
      </div>
    </div>
  )
}

function Metric({ k, v }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold mb-1">{k}</div>
      <div className="text-[20px] font-bold text-on-surface">{v}</div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const current = useCurrent()
  const { files, setFile, settings, updateSetting, isReadyToGenerate, startProcessing,
          selectedPrograms, setSelectedPrograms } = useScheduler()
  const { toasts, toast, dismiss } = useToast()

  const [configTab,  setConfigTab]  = useState('programmes')
  const [uploading,  setUploading]  = useState({})

  const filesUploaded = Object.values(files).filter(Boolean).length

  const handleFileSelect = useCallback(async (key, file) => {
    if (!file) { setFile(key, null); return }
    setFile(key, file)
    setUploading(p => ({ ...p, [key]: true }))
    try {
      await UPLOAD_FN[key](file)
      toast(`${file.name} uploaded successfully.`, 'success')
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Upload failed (${err.status}): ${err.message}`
        : 'Upload failed — backend may not be running.'
      toast(msg, 'warning')
    } finally {
      setUploading(p => ({ ...p, [key]: false }))
    }
  }, [setFile, toast])

  const handleGenerate = async () => {
    await startProcessing()
    navigate('/processing')
  }

  return (
    <WorkspaceShell
      current={current}
      title="Dashboard Overview"
      subtitle="Initialize Session"
      right={
        <button className="glass btn-ghost rounded-full px-4 py-2 text-[11px] uppercase tracking-[0.12em] font-semibold text-on-surface flex items-center gap-2 mr-2">
          <span className="w-1.5 h-1.5 rounded-full bg-primary pulse-soft" />
          Engine v4.2.0
        </button>
      }
    >
      <div className="screen-anim space-y-12">

        {/* Hero */}
        <section className="grid grid-cols-12 gap-6 items-end">
          <div className="col-span-12 lg:col-span-8">
            <p className="text-[11px] uppercase tracking-[0.22em] text-on-surface-variant/60 font-semibold mb-3">Initialize session</p>
            <h1 className="text-[44px] md:text-[56px] font-extrabold tracking-tight leading-[1.05] mb-4 text-balance">
              Upload your datasets to begin <span className="grad-text-cool">orchestration</span>.
            </h1>
            <p className="text-on-surface-variant/75 text-[15px] max-w-2xl leading-relaxed">
              The Syncademic engine will optimize classroom utility and minimize student conflicts across faculties. Three timelines are streamed in parallel.
            </p>
          </div>
          <div className="col-span-12 lg:col-span-4">
            <div className="glass rounded-2xl p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">Data integrity</span>
                <span className="text-[11px] font-bold text-primary">{Math.round((filesUploaded / 3) * 100)}%</span>
              </div>
              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden mb-3">
                <div className="h-full transition-all duration-700"
                  style={{ width: `${(filesUploaded / 3) * 100}%`, background: 'linear-gradient(90deg,#3b82f6,#8b5cf6)', boxShadow: '0 0 12px rgba(173,198,255,0.5)' }} />
              </div>
              <p className="text-[11px] text-on-surface-variant/60">{filesUploaded} of 3 datasets validated</p>
            </div>
          </div>
        </section>

        {/* Upload cards */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {UPLOAD_CARDS.map(card => (
            <DataCard
              key={card.key}
              config={card}
              file={files[card.key]}
              uploading={uploading[card.key]}
              onSelect={f => handleFileSelect(card.key, f)}
            />
          ))}
        </section>

        {/* Summary tiles */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-5">
          {[
            { k: 'Active cohort',  v: '8,412', d: '↑ 6.2% YoY',         tone: 'primary',   icon: 'groups'       },
            { k: 'Exams to place', v: '142',   d: 'across 12 faculties', tone: 'secondary', icon: 'assignment'   },
            { k: 'Venues',         v: '37',    d: '88% utilization',     tone: 'tertiary',  icon: 'meeting_room' },
            { k: 'Days available', v: '21',    d: 'Dec 1 – Dec 21',      tone: 'primary',   icon: 'date_range'   },
          ].map(s => (
            <div key={s.k} className="glass glass-hover rounded-2xl p-5">
              <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold">{s.k}</span>
                <div className="w-8 h-8 rounded-lg glass-inner flex items-center justify-center">
                  <Icon name={s.icon} className={`text-[16px] ${s.tone === 'primary' ? 'text-primary' : s.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`} />
                </div>
              </div>
              <div className={`text-[30px] font-bold leading-none mb-1 ${s.tone === 'primary' ? 'text-primary' : s.tone === 'secondary' ? 'text-secondary' : 'text-tertiary'}`}>{s.v}</div>
              <div className="text-[11px] text-on-surface-variant/60">{s.d}</div>
            </div>
          ))}
        </section>

        {/* Recent runs + Constraints */}
        <section className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7 glass glass-hover rounded-3xl p-7">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold mb-2">Recent solver runs</p>
                <h3 className="text-[22px] font-semibold">Last 7 days</h3>
              </div>
              <Chip tone="primary">Online</Chip>
            </div>
            <div className="flex items-end gap-3 h-32">
              {[35, 52, 48, 78, 64, 92, 88, 100].map((v, i) => {
                const labels = ['18', '19', '20', '21', '22', '23', '24', '25']
                const active = i === 7
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-2 group">
                    <div className="text-[10px] font-bold text-on-surface-variant/40 group-hover:text-primary transition-colors">{v === 100 ? 18 : Math.round(v * 18 / 100)}</div>
                    <div className="w-full rounded-t-lg transition-all relative" style={{
                      height: `${v}%`,
                      background: active ? 'linear-gradient(180deg, #adc6ff 0%, rgba(139,92,246,0.4) 100%)' : 'rgba(173,198,255,0.18)',
                      boxShadow: active ? '0 0 20px rgba(173,198,255,0.4)' : 'none',
                    }} />
                    <div className="text-[9px] uppercase tracking-widest text-on-surface-variant/50">May {labels[i]}</div>
                  </div>
                )
              })}
            </div>
            <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-white/5">
              <Metric k="Avg solve time" v="11.4s" />
              <Metric k="Solver health" v="99.8%" />
              <Metric k="Conflicts resolved" v="2,847" />
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5 glass glass-hover rounded-3xl p-7">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-on-surface-variant/60 font-semibold mb-2">Active constraints</p>
                <h3 className="text-[22px] font-semibold">8 hard rules</h3>
              </div>
              <button className="glass-inner rounded-full px-3 py-1.5 text-[11px] font-semibold text-on-surface-variant hover:text-primary transition-colors">
                <Icon name="tune" className="text-[14px] mr-1 align-middle" /> Adjust
              </button>
            </div>
            <div className="space-y-3">
              {[
                { l: 'No back-to-back examinations within 12h',  on: true  },
                { l: 'Religious holidays (3 calendars)',           on: true  },
                { l: 'Min 2-day study gap between disciplines',   on: true  },
                { l: 'Venue capacity ≤ 1.05× enrolled',           on: true  },
                { l: 'Accessibility-first room assignment',        on: true  },
                { l: 'Faculty workload caps',                      on: false },
              ].map((c, i) => (
                <div key={i} className="glass-inner rounded-xl px-4 py-3 flex items-center justify-between">
                  <span className="text-[13px] text-on-surface-variant flex items-center gap-3">
                    <span className="w-1.5 h-1.5 rounded-full" style={{
                      background: c.on ? '#adc6ff' : 'rgba(255,255,255,0.2)',
                      boxShadow: c.on ? '0 0 8px rgba(173,198,255,0.6)' : 'none',
                    }} />
                    {c.l}
                  </span>
                  <div className="w-9 h-5 rounded-full relative transition-all" style={{ background: c.on ? 'rgba(173,198,255,0.25)' : 'rgba(255,255,255,0.08)' }}>
                    <div className="w-4 h-4 rounded-full absolute top-0.5 transition-all" style={{
                      left: c.on ? 'calc(100% - 18px)' : '2px',
                      background: c.on ? '#adc6ff' : 'rgba(255,255,255,0.3)',
                      boxShadow: c.on ? '0 0 10px rgba(173,198,255,0.7)' : 'none',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA strip */}
        <section
          className="rounded-[28px] p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-8 relative overflow-hidden"
          style={{
            background: 'linear-gradient(135deg, rgba(59,130,246,0.10), rgba(139,92,246,0.10))',
            border: '1px solid rgba(173,198,255,0.18)',
            backdropFilter: 'blur(40px)',
          }}
        >
          <div className="absolute -inset-px rounded-[28px] pointer-events-none" style={{
            background: 'radial-gradient(40% 60% at 20% 20%, rgba(59,130,246,0.18), transparent 70%), radial-gradient(40% 60% at 80% 80%, rgba(139,92,246,0.18), transparent 70%)',
          }} />
          <div className="relative max-w-xl">
            <Chip tone={isReadyToGenerate ? 'primary' : 'tertiary'} className="mb-3">
              {isReadyToGenerate ? 'All systems go' : `${3 - filesUploaded} dataset${3 - filesUploaded === 1 ? '' : 's'} pending`}
            </Chip>
            <h3 className="text-[28px] md:text-[32px] font-bold leading-tight mb-2">Ready to orchestrate?</h3>
            <p className="text-on-surface-variant/75 text-[14px] leading-relaxed">
              Review your data integrity or proceed to generate the optimal schedule. You can manually adjust parameters in the next step.
            </p>
          </div>
          <div className="relative flex flex-col sm:flex-row gap-3 w-full md:w-auto">
            <GhostButton size="md" icon="add">Add course manually</GhostButton>
            <GradButton size="md" icon="auto_awesome" onClick={handleGenerate} disabled={!isReadyToGenerate}>
              Generate schedule
            </GradButton>
          </div>
        </section>

        {/* Configure Session */}
        {isReadyToGenerate && (
          <section>
            <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
              <div>
                <h2 className="text-[28px] font-bold tracking-tight mb-1">Configure Session</h2>
                <p className="text-on-surface-variant/70 text-[14px]">Select programmes, browse courses, and tune exam period windows.</p>
              </div>
              <div className="flex glass-inner p-1 rounded-full gap-1">
                {[
                  { key: 'programmes', label: 'Programmes & Courses', icon: 'school'    },
                  { key: 'periods',    label: 'Exam Periods',         icon: 'date_range' },
                ].map(tab => (
                  <button key={tab.key} onClick={() => setConfigTab(tab.key)}
                    className="flex items-center gap-2 px-4 py-2 rounded-full text-[12px] uppercase tracking-[0.08em] font-semibold transition-all"
                    style={configTab === tab.key ? {
                      background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                      color: '#fff',
                      boxShadow: '0 0 14px rgba(173,198,255,0.4)',
                    } : { color: 'rgba(218,226,253,0.6)' }}>
                    <Icon name={tab.icon} className="text-[16px]" />
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {configTab === 'programmes' ? (
              <div className="grid gap-5" style={{ gridTemplateColumns: '300px 1fr' }}>
                <ProgrammePanel selected={selectedPrograms} onChange={setSelectedPrograms} toast={toast} />
                <CourseAccordion selectedPrograms={selectedPrograms} programmes={[]} toast={toast} />
              </div>
            ) : (
              <ExamPeriodCalendar toast={toast} />
            )}
          </section>
        )}
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </WorkspaceShell>
  )
}
