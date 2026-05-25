import { useState, useCallback, useRef } from 'react'
import { PIPELINE_STEPS } from '../models/types'

/**
 * Central state hook for the exam scheduling pipeline.
 *
 * Mirrors the AppController pipeline:
 *   1. Load files (courses.txt, dates.txt, programs.txt)
 *   2. POST /api/generate → AppController.run()
 *   3. Stream processing steps via SSE or polling
 *   4. Receive Schedule[] results → display in ResultsView / DetailedCalendar
 */
export function useScheduler() {
  // ── File inputs — bound to Python file readers ─────────────────────────
  const [files, setFiles] = useState({
    courses:  null,   // → course_file_reader.py
    dates:    null,   // → exam_period_file_reader.py
    programs: null,   // → program_selector_reader.py
  })

  // ── Program selection (derived from programs.txt parsing) ──────────────
  const [selectedPrograms, setSelectedPrograms] = useState([])

  // ── Settings (global config applied before generation) ────────────────
  // TODO: wire to Settings sidebar panel
  const [settings, setSettings] = useState({
    restDays:        [],      // days of week blocked (0=Sun … 6=Sat)
    holidayDates:    [],      // ISO date strings from holiday upload
    minGapDays:      1,       // minimum study gap between exams
    preferEarlyMoed: true,
  })

  // ── Processing state — mirrors AppController pipeline stages ──────────
  const [processingState, setProcessingState] = useState({
    isRunning:   false,
    isPaused:    false,
    progress:    0,           // 0–100
    currentStep: -1,
    steps: PIPELINE_STEPS.map(label => ({
      label,
      status:  'pending',     // 'pending' | 'running' | 'done' | 'error'
      elapsed: null,          // seconds
    })),
    engineLoad: 0,            // 0–100 CPU %
    logs:       [],           // string[]
  })

  // ── Results from AppController.run() export ────────────────────────────
  const [results, setResults] = useState(null)

  // ── Internal: polling/SSE handle ──────────────────────────────────────
  const pollRef = useRef(null)

  // ── Actions ───────────────────────────────────────────────────────────

  const setFile = useCallback((key, file) => {
    setFiles(prev => ({ ...prev, [key]: file }))
  }, [])

  const updateSetting = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const isReadyToGenerate = Boolean(files.courses && files.dates && files.programs)

  const startProcessing = useCallback(async () => {
    if (!isReadyToGenerate) return

    setProcessingState(prev => ({
      ...prev,
      isRunning:   true,
      isPaused:    false,
      progress:    0,
      currentStep: 0,
      steps:       prev.steps.map(s => ({ ...s, status: 'pending', elapsed: null })),
      logs:        ['[ENGINE] Initializing constraint solver...'],
      engineLoad:  0,
    }))

    // TODO: replace with real API call
    // const formData = new FormData()
    // formData.append('courses',  files.courses)
    // formData.append('dates',    files.dates)
    // formData.append('programs', files.programs)
    // formData.append('settings', JSON.stringify(settings))
    // const res = await fetch('/api/generate', { method: 'POST', body: formData })
    // const data = await res.json()
    // setResults(data.schedules)
  }, [isReadyToGenerate, files, settings])

  const pauseProcessing = useCallback(() => {
    setProcessingState(prev => ({ ...prev, isPaused: !prev.isPaused }))
    // TODO: POST /api/pause
  }, [])

  const cancelProcessing = useCallback(() => {
    clearInterval(pollRef.current)
    setProcessingState(prev => ({
      ...prev,
      isRunning:   false,
      isPaused:    false,
      progress:    0,
      currentStep: -1,
      steps:       prev.steps.map(s => ({ ...s, status: 'pending', elapsed: null })),
      logs:        [],
      engineLoad:  0,
    }))
    // TODO: POST /api/cancel
  }, [])

  // Called by ProcessingState to update individual step status
  // (will be driven by SSE events from the Python backend)
  const updateStep = useCallback((stepIndex, patch) => {
    setProcessingState(prev => {
      const steps = prev.steps.map((s, i) => i === stepIndex ? { ...s, ...patch } : s)
      const doneCount = steps.filter(s => s.status === 'done').length
      const progress  = Math.round((doneCount / steps.length) * 100)
      return { ...prev, steps, progress, currentStep: stepIndex }
    })
  }, [])

  const appendLog = useCallback((line) => {
    setProcessingState(prev => ({ ...prev, logs: [...prev.logs, line] }))
  }, [])

  return {
    files,
    setFile,
    selectedPrograms,
    setSelectedPrograms,
    settings,
    updateSetting,
    processingState,
    results,
    setResults,
    isReadyToGenerate,
    startProcessing,
    pauseProcessing,
    cancelProcessing,
    updateStep,
    appendLog,
  }
}
