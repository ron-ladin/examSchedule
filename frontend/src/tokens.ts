/**
 * Strict readonly tuple containing the 5 distinct colors for study programmes.
 * Derived directly from Niv's Python design tokens to keep things synced.
 * TypeScript enforces this as a fixed set of exactly 5 entries.
 */
export const PROGRAMME_COLOURS = [
  '#d0bcff', // Slot 1: Lavender accent
  '#adc6ff', // Slot 2: Crystal Blue accent
  '#34d399', // Slot 3: Mint Green (Success/Valid)
  '#fbbf24', // Slot 4: Amber/Warning
  '#f87171'  // Slot 5: Coral/Danger
] as const;
