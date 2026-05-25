/**
 * SCRUM-87 — MSW browser worker entry point.
 * Imported by src/main.jsx in development mode only.
 */

import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)
