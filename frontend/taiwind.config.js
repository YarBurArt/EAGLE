/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          app: '#0d1117',
          nav: '#161b22',
          card: '#161b22',
          'card-hover': '#1c2333',
          input: '#0d1117',
          dropdown: '#161b22',
        },
        border: {
          subtle: '#21262d',
          default: '#30363d',
          strong: '#484f58',
          accent: '#3679dd',
        },
        text: {
          primary: '#c9d1d9',
          secondary: '#8b949e',
          muted: '#6e7681',
        },
        accent: '#58a6ff',
        danger: '#dd6760',
        success: '#61c06d',
        warning: '#d29922',
      },
      fontFamily: {
        mono: ['Consolas', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [],
}
