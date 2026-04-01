module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}"
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: '#0066cc',
        secondary: '#1e40af',
        accent: '#f59e0b',
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        dark: '#0f172a',
        'dark-secondary': '#1e293b',
        'dark-tertiary': '#334155'
      },
      backgroundColor: {
        'dark-primary': '#0f172a',
        'dark-secondary': '#1e293b',
        'dark-tertiary': '#334155'
      },
      textColor: {
        'dark-primary': '#f1f5f9',
        'dark-secondary': '#cbd5e1'
      },
      keyframes: {
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '.5' }
        },
        blink: {
          '0%, 49%': { opacity: '1' },
          '50%, 100%': { opacity: '0' }
        }
      },
      animation: {
        pulse: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        blink: 'blink 1s steps(1, start) infinite'
      }
    }
  },
  plugins: []
}
