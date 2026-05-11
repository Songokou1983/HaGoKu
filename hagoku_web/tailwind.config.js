/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "app-bg":            '#0A0E1A',
        "app-bg-secondary":  '#111827',
        "app-bg-tertiary":   '#1F2937',
        "app-text":          '#F9FAFB',
        "app-text-muted":    '#9CA3AF',
        "app-accent":        '#3B82F6',
        "app-accent-hover":  '#2563EB',
        "app-border":        '#374151',
        "app-error":         '#EF4444',
        "app-success":       '#10B981',
        "app-warning":       '#F59E0B',
      },
      fontSize: {
        "ui-xs":   ['11px', { lineHeight: '16px' }],
        "ui-sm":   ['12px', { lineHeight: '18px' }],
        "ui-base": ['13px', { lineHeight: '20px' }],
        "ui-md":   ['14px', { lineHeight: '22px' }],
      },
      fontFamily: {
        sans: ['Fira Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['Fira Code', 'Cascadia Code', 'JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
