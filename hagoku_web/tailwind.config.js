/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "app-bg": "#1e1e1e",
        "app-bg-secondary": "#252525",
        "app-text": "#d4d4d4",
        "app-text-muted": "#888",
        "app-accent": "#569cd6",
        "app-border": "#333",
      },
    },
  },
  plugins: [],
};