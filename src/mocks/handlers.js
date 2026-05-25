/**
 * SCRUM-87 — MSW request handlers for all Syncademic API endpoints.
 * Used in development; imported by src/mocks/browser.js.
 *
 * Mirrors every endpoint in src/api/client.js so the UI runs without a live backend.
 */

import { http, HttpResponse } from 'msw'

// ── Shared mock data ───────────────────────────────────────────────────────

const PROGRAMMES = [
  { id: '83101', name: 'Computer Science',       courseCount: 42 },
  { id: '83201', name: 'Mathematics',            courseCount: 31 },
  { id: '83301', name: 'Software Engineering',   courseCount: 38 },
  { id: '83401', name: 'Information Systems',    courseCount: 27 },
  { id: '83501', name: 'Data Science',           courseCount: 24 },
  { id: '83601', name: 'Electrical Engineering', courseCount: 45 },
]

const COURSES_BY_PROGRAMME = {
  '83101': [
    { id: '10101', name: 'Introduction to CS',        instructor: 'Prof. A. Cohen',  evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '10102', name: 'Discrete Mathematics',       instructor: 'Dr. M. Levy',     evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '10201', name: 'Data Structures',            instructor: 'Dr. E. Golan',    evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '10202', name: 'Algorithms',                 instructor: 'Prof. R. Chen',   evaluationType: 'Exam',    offerings: [{ programId: '83101', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '10301', name: 'Software Engineering Project', instructor: 'Dr. S. Bar',   evaluationType: 'Project', offerings: [{ programId: '83101', year: 3, semester: 'FALL', requirement: 'Obligatory' }] },
  ],
  '83201': [
    { id: '20101', name: 'Calculus 1',     instructor: 'Prof. O. Some', evaluationType: 'Exam', offerings: [{ programId: '83201', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '20102', name: 'Linear Algebra', instructor: 'Dr. Y. Klein',  evaluationType: 'Exam', offerings: [{ programId: '83201', year: 1, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '20201', name: 'Calculus 2',     instructor: 'Prof. O. Some', evaluationType: 'Exam', offerings: [{ programId: '83201', year: 2, semester: 'FALL', requirement: 'Obligatory' }] },
  ],
  '83301': [
    { id: '30101', name: 'Object-Oriented Programming', instructor: 'Dr. N. Cohen', evaluationType: 'Exam',    offerings: [{ programId: '83301', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '30201', name: 'Database Systems',            instructor: 'Prof. B. Tal', evaluationType: 'Exam',    offerings: [{ programId: '83301', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '30301', name: 'Capstone Project',            instructor: 'Dr. T. Rosen', evaluationType: 'Project', offerings: [{ programId: '83301', year: 3, semester: 'SUMM', requirement: 'Obligatory' }] },
  ],
  '83401': [
    { id: '40101', name: 'Information Systems Intro', instructor: 'Prof. A. Ben', evaluationType: 'Exam', offerings: [{ programId: '83401', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '40201', name: 'Business Intelligence',     instructor: 'Dr. K. Alon',  evaluationType: 'Exam', offerings: [{ programId: '83401', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
  ],
  '83501': [
    { id: '50101', name: 'Statistics for DS',  instructor: 'Prof. L. Dana', evaluationType: 'Exam',       offerings: [{ programId: '83501', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '50201', name: 'Machine Learning',   instructor: 'Dr. V. Oren',   evaluationType: 'Exam',       offerings: [{ programId: '83501', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
    { id: '50202', name: 'Deep Learning Lab',  instructor: 'Dr. V. Oren',   evaluationType: 'Attendance', offerings: [{ programId: '83501', year: 2, semester: 'SPRI', requirement: 'Elective' }] },
  ],
  '83601': [
    { id: '60101', name: 'Circuit Theory',    instructor: 'Prof. E. Shir', evaluationType: 'Exam', offerings: [{ programId: '83601', year: 1, semester: 'FALL', requirement: 'Obligatory' }] },
    { id: '60201', name: 'Signals & Systems', instructor: 'Dr. Y. Ron',    evaluationType: 'Exam', offerings: [{ programId: '83601', year: 2, semester: 'SPRI', requirement: 'Obligatory' }] },
  ],
}

let periods = [
  { key: 'FALL-Aleph', semester: 'FALL', moed: 'Aleph', startDate: '2025-01-12', endDate: '2025-02-06', excludedDates: ['2025-01-20', '2025-01-27'] },
  { key: 'FALL-Bet',   semester: 'FALL', moed: 'Bet',   startDate: '2025-02-16', endDate: '2025-03-06', excludedDates: [] },
  { key: 'SPRI-Aleph', semester: 'SPRI', moed: 'Aleph', startDate: '2025-06-15', endDate: '2025-07-10', excludedDates: ['2025-06-22'] },
  { key: 'SPRI-Bet',   semester: 'SPRI', moed: 'Bet',   startDate: '2025-07-20', endDate: '2025-08-07', excludedDates: [] },
]

const MOCK_ASSIGNMENTS = [
  { courseId: '10202', courseName: 'Algorithms',                 instructor: 'Prof. R. Chen',  date: '2025-01-14', conflicts: 0 },
  { courseId: '10201', courseName: 'Data Structures',            instructor: 'Dr. E. Golan',   date: '2025-01-17', conflicts: 0 },
  { courseId: '10102', courseName: 'Discrete Mathematics',       instructor: 'Dr. M. Levy',    date: '2025-01-21', conflicts: 1 },
  { courseId: '20201', courseName: 'Calculus 2',                 instructor: 'Prof. O. Some',  date: '2025-01-24', conflicts: 0 },
  { courseId: '30201', courseName: 'Database Systems',           instructor: 'Prof. B. Tal',   date: '2025-01-28', conflicts: 0 },
  { courseId: '10101', courseName: 'Introduction to CS',         instructor: 'Prof. A. Cohen', date: '2025-01-31', conflicts: 0 },
  { courseId: '50201', courseName: 'Machine Learning',           instructor: 'Dr. V. Oren',    date: '2025-02-04', conflicts: 0 },
]

const MOCK_SCHEDULES = [
  { id: 'sched-optimal', periodKey: 'FALL-Aleph', assignments: MOCK_ASSIGNMENTS, totalConflicts: 1, durationDays: 21, avgStudyGap: 3.2, resourceLoad: 'Moderate' },
  { id: 'sched-fastest', periodKey: 'FALL-Aleph', assignments: MOCK_ASSIGNMENTS, totalConflicts: 3, durationDays: 14, avgStudyGap: 1.8, resourceLoad: 'Intense'  },
  { id: 'sched-relaxed', periodKey: 'FALL-Aleph', assignments: MOCK_ASSIGNMENTS, totalConflicts: 0, durationDays: 28, avgStudyGap: 4.5, resourceLoad: 'Minimal'  },
]

// ── Handlers ───────────────────────────────────────────────────────────────

export const handlers = [

  // GET /api/data/status
  http.get('/api/data/status', () =>
    HttpResponse.json({ courses: true, periods: true, programmes: true })
  ),

  // POST /api/data/courses/upload
  http.post('/api/data/courses/upload', () =>
    HttpResponse.json({ message: 'Courses uploaded (mock).', courseCount: 42 })
  ),

  // POST /api/data/periods/upload
  http.post('/api/data/periods/upload', () =>
    HttpResponse.json({ message: 'Periods uploaded (mock).', periodCount: 4 })
  ),

  // GET /api/programmes
  http.get('/api/programmes', () => HttpResponse.json(PROGRAMMES)),

  // GET /api/programmes/:id/courses
  http.get('/api/programmes/:id/courses', ({ params }) => {
    const courses = COURSES_BY_PROGRAMME[params.id]
    if (!courses) return HttpResponse.json([], { status: 200 })
    return HttpResponse.json(courses)
  }),

  // GET /api/periods
  http.get('/api/periods', () => HttpResponse.json(periods)),

  // PATCH /api/periods/:key/exclusions
  http.patch('/api/periods/:key/exclusions', async ({ params, request }) => {
    const body = await request.json()
    periods = periods.map(p =>
      p.key === params.key ? { ...p, excludedDates: body.excludedDates } : p
    )
    return HttpResponse.json({ message: 'Exclusions updated (mock).' })
  }),

  // PATCH /api/periods/:key/range
  http.patch('/api/periods/:key/range', async ({ params, request }) => {
    const body = await request.json()
    periods = periods.map(p =>
      p.key === params.key ? { ...p, startDate: body.startDate, endDate: body.endDate } : p
    )
    return HttpResponse.json({ message: 'Range updated (mock).' })
  }),

  // POST /api/generate
  http.post('/api/generate', async () => {
    await new Promise(r => setTimeout(r, 800))
    return HttpResponse.json({ jobId: 'job-mock-001' })
  }),

  // GET /api/schedules
  http.get('/api/schedules', ({ request }) => {
    const url  = new URL(request.url)
    const page = parseInt(url.searchParams.get('page')     ?? '1', 10)
    const size = parseInt(url.searchParams.get('pageSize') ?? '10', 10)
    return HttpResponse.json({
      schedules: MOCK_SCHEDULES,
      total:     MOCK_SCHEDULES.length,
      page,
      pageSize:  size,
    })
  }),

  // GET /api/schedules/:id/export
  http.get('/api/schedules/:id/export', ({ params }) => {
    const schedule = MOCK_SCHEDULES.find(s => s.id === params.id) ?? MOCK_SCHEDULES[0]
    const lines = [
      `Syncademic Export — ${schedule.periodKey}`,
      `Generated: ${new Date().toISOString()}`,
      '',
      ...schedule.assignments.map(a => `${a.date}  ${a.courseId}  ${a.courseName}  (${a.instructor})`),
    ]
    return new HttpResponse(lines.join('\n'), {
      headers: {
        'Content-Type': 'text/plain',
        'Content-Disposition': `attachment; filename="${schedule.id}.txt"`,
      },
    })
  }),
]
