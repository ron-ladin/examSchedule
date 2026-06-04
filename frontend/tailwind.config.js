/** @type {import('tailwindcss').Config} */
module.exports = {
  // Tells Tailwind which files to look at for design classes
  content: [
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // 1. Color System (Matches Niv's Python colors exactly)
      colors: {
        brand: {
          primary: '#adc6ff',    // Crystal Blue - Used for main texts and highlights
          secondary: '#d0bcff',  // Lavender - Used for secondary highlights and tabs
          success: '#34d399',    // Mint Green - Used for successful states
          warning: '#fbbf24',    // Amber - Used for warnings or pending actions
          danger: '#f87171',     // Coral - Used for error boxes and alerts
          neutral: '#adbac7',    // Muted Grey - Used for normal layout borders and descriptions
          excluded: '#dc2626',   // Bold Red - Used for excluded days and text in ErrorBoundary
        },
        surface: {
          base: '#0b1326',       // Main dark background of the application window
          raised: '#060e20',     // Dark background for the sidebar panel
          overlay: '#131b2e',    // Background color for inner cards and group boxes
          hover: '#1e2b45',      // Background color when hovering with the mouse
        },
        exam: {
          mandatory: '#adc6ff',  // Crystal Blue background for mandatory exam items
          elective: '#d0bcff',   // Lavender background for elective exam items
          excluded: '#fee2e2',   // Light red background for excluded days on the calendar
          validDate: '#dbeafe',  // Light blue background for active open days on the calendar
        }
      },
      
      // 2. Typography Standard (Font family token)
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'], // Professional, clean font style
      },
      
      // 3. Layout Spacing Tokens (Matches the Python layout spacing values)
      spacing: {
        'calendar-cell': '30px',  // The exact 30px size for calendar day cells from Python
        'panel-gap': '12px',      // The exact 12px layout gap between different screens
      }
    },
  },
  plugins: [],
}