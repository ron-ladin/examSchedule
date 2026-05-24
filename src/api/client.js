/**
 * SCRUM-80 — Typed API client for the Syncademic backend.
 * All endpoints proxy through Vite → http://localhost:8000
 *
 * Usage:
 *   import { api } from './api/client'
 *   const programmes = await api.getProgrammes()
 */

const BASE = '/api'

// ── Error type ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.name    = 'ApiError'
    this.status  = status
    this.body    = body
  }
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const url = `${BASE}${path}`
  const res = await fetch(url, {
    headers: options.body instanceof FormData
      ? {}                                        // browser sets multipart boundary
      : { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })

  if (!res.ok) {
    let body = null
    try { body = await res.json() } catch { /* ignore */ }
    throw new ApiError(res.status, body?.detail ?? res.statusText, body)
  }

  if (res.status === 204) return null
  return res.json()
}

// ── Data upload endpoints (SCRUM-67, SCRUM-68) ───────────────────────────────

/**
 * Upload courses.txt → course_file_reader.py
 * @param {File} file
 * @returns {Promise<{message: string, courseCount: number}>}
 */
function uploadCourses(file) {
  const fd = new FormData()
  fd.append('file', file)
  return apiFetch('/data/courses/upload', { method: 'POST', body: fd })
}

/**
 * Upload dates.txt → exam_period_file_reader.py
 * @param {File} file
 * @returns {Promise<{message: string, periodCount: number}>}
 */
function uploadPeriods(file) {
  const fd = new FormData()
  fd.append('file', file)
  return apiFetch('/data/periods/upload', { method: 'POST', body: fd })
}

// ── Data status (SCRUM-69) ────────────────────────────────────────────────────

/**
 * @returns {Promise<{courses: boolean, periods: boolean, programmes: boolean}>}
 */
function getDataStatus() {
  return apiFetch('/data/status')
}

// ── Programme endpoints (SCRUM-70, SCRUM-71) ─────────────────────────────────

/**
 * @returns {Promise<Array<{id: string, name: string, courseCount: number}>>}
 */
function getProgrammes() {
  return apiFetch('/programmes')
}

/**
 * @param {string} programmeId
 * @returns {Promise<Array<{id: string, name: string, evaluationType: string, offerings: Array}>>}
 */
function getProgrammeCourses(programmeId) {
  return apiFetch(`/programmes/${encodeURIComponent(programmeId)}/courses`)
}

// ── Period endpoints (SCRUM-72, SCRUM-73, SCRUM-74) ──────────────────────────

/**
 * @returns {Promise<Array<{key: string, semester: string, moed: string, startDate: string, endDate: string, excludedDates: string[]}>>}
 */
function getPeriods() {
  return apiFetch('/periods')
}

/**
 * @param {string} periodKey  e.g. "FALL-Aleph"
 * @param {string[]} excludedDates  ISO date strings
 */
function updatePeriodExclusions(periodKey, excludedDates) {
  return apiFetch(`/periods/${encodeURIComponent(periodKey)}/exclusions`, {
    method: 'PATCH',
    body: JSON.stringify({ excludedDates }),
  })
}

/**
 * @param {string} periodKey
 * @param {string} startDate  ISO date
 * @param {string} endDate    ISO date
 */
function updatePeriodRange(periodKey, startDate, endDate) {
  return apiFetch(`/periods/${encodeURIComponent(periodKey)}/range`, {
    method: 'PATCH',
    body: JSON.stringify({ startDate, endDate }),
  })
}

// ── Schedule generation (implied by ProcessingState / AppController) ──────────

/**
 * Kick off the CSP engine.
 * @param {{courses: File, dates: File, programs: File, settings: object}} payload
 * @returns {Promise<{jobId: string}>}
 */
function generateSchedule({ courses, dates, programs, settings }) {
  const fd = new FormData()
  fd.append('courses',  courses)
  fd.append('dates',    dates)
  fd.append('programs', programs)
  fd.append('settings', JSON.stringify(settings))
  return apiFetch('/generate', { method: 'POST', body: fd })
}

/**
 * Pause the running engine.
 */
function pauseGeneration() {
  return apiFetch('/pause', { method: 'POST' })
}

/**
 * Cancel the running engine.
 */
function cancelGeneration() {
  return apiFetch('/cancel', { method: 'POST' })
}

// ── Schedule results (SCRUM-77, SCRUM-78) ────────────────────────────────────

/**
 * @param {{page?: number, pageSize?: number}} opts
 * @returns {Promise<{schedules: Array, total: number, page: number, pageSize: number}>}
 */
function getSchedules({ page = 1, pageSize = 10 } = {}) {
  return apiFetch(`/schedules?page=${page}&pageSize=${pageSize}`)
}

/**
 * Download a schedule as a text file blob.
 * @param {string} scheduleId
 * @returns {Promise<Blob>}
 */
async function exportSchedule(scheduleId) {
  const res = await fetch(`${BASE}/schedules/${encodeURIComponent(scheduleId)}/export`)
  if (!res.ok) throw new ApiError(res.status, res.statusText, null)
  return res.blob()
}

// ── Unified export ────────────────────────────────────────────────────────────

export const api = {
  // data upload
  uploadCourses,
  uploadPeriods,
  getDataStatus,
  // programmes
  getProgrammes,
  getProgrammeCourses,
  // periods
  getPeriods,
  updatePeriodExclusions,
  updatePeriodRange,
  // generation
  generateSchedule,
  pauseGeneration,
  cancelGeneration,
  // results
  getSchedules,
  exportSchedule,
}
