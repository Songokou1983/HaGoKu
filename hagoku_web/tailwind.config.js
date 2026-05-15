/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 背景略抬一点层次，正文用灰白而非刺眼的近纯白
        "app-bg":            '#121826',
        "app-bg-secondary":  '#131A28',
        "app-bg-tertiary":   '#222A3A',
        "app-text":          '#E2E5EB',
        "app-text-muted":    '#B8BFCA',
        "app-accent":        '#3B82F6',
        "app-accent-hover":  '#2563EB',
        "app-border":        '#3D4658',
        "app-error":         '#EF4444',
        "app-error-hover":   '#DC2626',
        "app-success":       '#10B981',
        "app-success-hover":  '#059669',
        "app-warning":       '#F59E0B',
        "app-warning-hover": '#D97706',
        // Status badge backgrounds
        "app-running":       '#1a3a5c',
        "app-done":          '#1a3a1a',
        "app-status-error":  '#3a1a1a',
        "app-status-waiting": '#3a3a1a',
        // Agent text (VS Code bright blue)
        "app-agent":         '#9cdcfe',
        // Event type colors
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
