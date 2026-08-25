/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        orion: { bg: '#020617', panel: '#0f172a', accent: '#38bdf8',
                 up: '#22c55e', down: '#ef4444' },
      },
    },
  },
  plugins: [],
};
