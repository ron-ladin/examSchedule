/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          // Core brand palette (matches design-system CSS variables)
          primary: '#440154',
          secondary: '#21918C',
          cta: '#FDE725',
          'cta-text': '#1A1A2E',
          // System states
          success: '#15b37e',
          warning: '#f59e0b',
          danger: '#f14545',
          neutral: '#6b7280',
          // Exam-specific indicators
          mandatory: '#eb545e',
          elective: '#11883b',
          excluded: '#585d65',
          'valid-date': '#3173ee',
        },
        surface: {
          base: '#F5F5F5',
          raised: '#ffffff',
          overlay: '#1A1A2E',
        },
        // Programme slot colours — one per slot (max 5, viridis-inspired)
        prog: {
          1: '#440154',
          2: '#31688E',
          3: '#21918C',
          4: '#35B779',
          5: '#FDE725',
        },
      },
      fontFamily: {
        sans: ['Fira Sans', 'sans-serif'],
        mono: ['Fira Code', 'monospace'],
      },
      spacing: {
        'calendar-cell': '80px',
        'panel-gap': '1.5rem',
      },
    },
  },
  plugins: [],
}
