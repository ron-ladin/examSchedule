// One background class per programme slot — matches prog.1–5 in tailwind.config.js
export const PROGRAMME_COLOURS = [
  'bg-prog-1',
  'bg-prog-2',
  'bg-prog-3',
  'bg-prog-4',
  'bg-prog-5',
] as const

export type ProgrammeColour = typeof PROGRAMME_COLOURS[number]
