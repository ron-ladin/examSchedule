/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          // Basic system states
          primary: '#1b3783', 
          success: '#15b37e',
          danger: '#f14545',
          // Exam-specific indicators (Crucial for Niv's UI components)
          mandatory: '#eb545e',
          elective: '#11883b',
          excluded: '#585d65',
          validDate: '#3173ee',
        }
    },
    spacing: {
      'calendar-cell': '80px',
    }
    
    },
  },
  plugins: [],
}
