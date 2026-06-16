/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "app-bg":            'var(--app-bg, #0B0E14)',
        "app-bg-secondary":  'var(--app-bg-secondary, #11151E)',
        "app-bg-tertiary":   'var(--app-bg-tertiary, #1C2333)',
        "app-text":          'var(--app-text, #E2E5EB)',
        "app-text-muted":    'var(--app-text-muted, #8892A4)',
        "app-accent":        'var(--app-accent, #00D4AA)',
        "app-accent-hover":  'var(--app-accent-hover, #00B892)',
        "app-border":        'var(--app-border, #2A3040)',
        "app-error":         '#EF4444',
        "app-error-hover":   '#DC2626',
        "app-success":       '#10B981',
        "app-success-hover":  '#059669',
        "app-warning":       '#F59E0B',
        "app-warning-hover": '#D97706',
        "app-running":       '#1a3a5c',
        "app-done":          '#1a3a1a',
        "app-status-error":  '#3a1a1a',
        "app-status-waiting": '#3a3a1a',
        "app-agent":         '#9cdcfe',
        "event-run":    '#569cd6',
        "event-done":   '#6a9955',
        "event-fail":   '#f44747',
        "event-warn":   '#dcdcaa',
        "event-purple":  '#c586c0',
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
