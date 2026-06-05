/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0d0f1a',
          secondary: '#13162a',
          card: '#1a1e36',
          hover: '#1f2440',
        },
        border: {
          subtle: '#252a45',
          DEFAULT: '#2e3454',
        },
        amber: {
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
        },
        text: {
          primary: '#e8eaf6',
          secondary: '#9da3c8',
          muted: '#5c6391',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['Georgia', 'Cambria', 'serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-amber': 'pulseAmber 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: { '0%': { transform: 'translateY(8px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
        pulseAmber: { '0%, 100%': { boxShadow: '0 0 0 0 rgba(245, 158, 11, 0)' }, '50%': { boxShadow: '0 0 0 4px rgba(245, 158, 11, 0.15)' } },
      },
    },
  },
  plugins: [],
}
