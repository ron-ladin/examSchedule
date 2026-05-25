/**
 * Frontend data model — JS mirrors of Python backend domain entities.
 *
 * Python sources:
 *   src/domain/course.py          → Course
 *   src/domain/course_offering.py → CourseOffering
 *   src/domain/exam_period.py     → ExamPeriod
 *   src/domain/schedule.py        → Schedule / ExamAssignment
 *   src/domain/semester.py        → Semester normalization
 */

// ── Enum-like constants ──────────────────────────────────────────────────────

/** @type {Record<string, string>} Mirrors semester normalization in semester.py */
export const SEMESTER = {
  FALL: 'FALL',
  SPRI: 'SPRI',
  SUMM: 'SUMM',
}

/** @type {Record<string, string>} Moed labels shown in the UI */
export const MOED = {
  Aleph: 'Aleph',
  Bet:   'Bet',
  Gimel: 'Gimel',
}

/** @type {Record<string, string>} Evaluation types from Course.evaluation_type */
export const EVAL_TYPE = {
  Exam:       'Exam',
  Project:    'Project',
  Attendance: 'Attendance',
}

/** @type {Record<string, string>} Offering requirement field */
export const REQUIREMENT = {
  Obligatory: 'Obligatory',
  Elective:   'Elective',
}

// ── Display labels ───────────────────────────────────────────────────────────

export const SEMESTER_LABELS = {
  [SEMESTER.FALL]: 'Fall Semester',
  [SEMESTER.SPRI]: 'Spring Semester',
  [SEMESTER.SUMM]: 'Summer Semester',
}

export const MOED_LABELS = {
  [MOED.Aleph]: 'Moed A (Aleph)',
  [MOED.Bet]:   'Moed B (Bet)',
  [MOED.Gimel]: 'Resit (Gimel)',
}

// ── File binding constants ───────────────────────────────────────────────────

/**
 * Maps UI upload slots to their expected filenames.
 * Each key corresponds to a Python file reader adapter:
 *
 *   courses  → src/adapters/readers/course_file_reader.py
 *   dates    → src/adapters/readers/exam_period_file_reader.py
 *   programs → src/adapters/readers/program_selector_reader.py
 */
export const DATA_FILES = {
  COURSES:  'courses.txt',
  DATES:    'dates.txt',
  PROGRAMS: 'programs.txt',
}

// ── JSDoc type definitions ───────────────────────────────────────────────────

/**
 * Mirrors Python: CourseOffering (frozen dataclass)
 * @typedef {Object} CourseOffering
 * @property {string}      programId   — 5-digit program code, e.g. "83101"
 * @property {number}      year        — Study year (1 | 2 | 3)
 * @property {string}      semester    — FALL | SPRI | SUMM
 * @property {string}      requirement — Obligatory | Elective
 */

/**
 * Mirrors Python: Course (dataclass, eq=False on id)
 * @typedef {Object} Course
 * @property {string}          id             — 5-digit unique course ID
 * @property {string}          name
 * @property {string}          instructor
 * @property {string}          evaluationType — Exam | Project | Attendance
 * @property {CourseOffering[]} offerings
 */

/**
 * Mirrors Python: ExamPeriod (dataclass)
 * @typedef {Object} ExamPeriod
 * @property {string}                          semester
 * @property {string}                          moed
 * @property {{ start: string, end: string }[]} dateRanges  — ISO date strings
 * @property {string[]}                         excludedDates — ISO date strings
 */

/**
 * A single exam-to-date assignment within a generated schedule.
 * Mirrors the Schedule.assignments list from schedule.py.
 * @typedef {Object} ExamAssignment
 * @property {string} courseId
 * @property {string} courseName
 * @property {string} instructor
 * @property {string} date         — ISO date string (YYYY-MM-DD)
 * @property {number} conflicts    — count of student-group overlaps on same day
 */

/**
 * One complete schedule for a single ExamPeriod.
 * Mirrors output produced by AppController → ScheduleGenerator.
 * @typedef {Object} Schedule
 * @property {string}           periodKey    — e.g. "FALL - Aleph"
 * @property {ExamAssignment[]} assignments
 * @property {number}           totalConflicts
 * @property {number}           durationDays
 * @property {number}           avgStudyGap  — average days between consecutive exams
 * @property {'Minimal'|'Moderate'|'Intense'} resourceLoad
 */

// ── User roles for registration ──────────────────────────────────────────────

export const USER_ROLES = [
  'Department Chair',
  'Exam Coordinator',
  'Academic Registrar',
  'Faculty Administrator',
]

// ── Processing pipeline steps ────────────────────────────────────────────────
// Mirrors the stages executed by AppController.run() + ScheduleGenerator

export const PIPELINE_STEPS = [
  'Validating structural constraints...',
  'Building O(n²) conflict graph...',
  'Applying MCV heuristics...',
  'Executing CSP backtracking engine...',
]
